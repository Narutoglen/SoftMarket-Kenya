"""Server-rendered front office for the white-label CRM core (Milestone 1).

Stack: Django + Tailwind + HTMX (per the PRD). HTMX requests are detected via
the `HX-Request` header — list/delete views return partials or an
`HX-Redirect`, while plain requests get the full page.
"""

import json

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from decimal import Decimal

from .api import resolve_tenant
from .forms import AccountForm, ActivityForm, ContactForm, PublicLeadForm
from .models import (
    Account, Activity, AgentQuestion, AgentRun, AgentTask, Contact, DealRoom,
    IntegrationConfig, IntegrationMessage, Lead, Opportunity, PaymentEvent,
    Subject, Suggestion, Tenant, TenantStage,
)
from . import dealroom as dealroom_service
from . import payments as payments_service
from . import services
from . import trust as trust_service
from .agent import evidence as ledger
from .agent import queue as agent_queue
from .agent import runner as agent_runner


def get_tenant(request):
    tenant = resolve_tenant(request)
    if not tenant:
        raise Http404("CRM instance not found.")
    # Mark the demo state: an anonymous visitor on the PUBLIC company instance
    # (i.e. not logged in) is browsing the sample workspace. Authenticated
    # clients never see this flag.
    user = getattr(request, "user", None)
    tenant.is_demo = (
        not (user is not None and user.is_authenticated)
        and tenant.is_public
        and tenant.slug == "softmarket"
    )
    return tenant


def require_tenant_access(view_func):
    """Defensive auth gate for private tenants (the middleware is primary).

    Requires an authenticated member of the resolved tenant. Public tenants are
    always open. Most views rely on TenantAccessMiddleware; this decorator exists
    for any view reached outside the /crm/ path.
    """
    from functools import wraps

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        tenant = resolve_tenant(request)
        if tenant is None:
            raise Http404("CRM instance not found.")
        if tenant.is_public:
            return view_func(request, *args, **kwargs)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return view_func(request, *args, **kwargs)
        return redirect(f"{reverse('crm:tenant_login')}?instance={tenant.slug}")
    return _wrapped


def is_htmx(request):
    return request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------------------
# Client access gateway — real Django auth (per-user login / sign-up)
# ---------------------------------------------------------------------------
@require_GET
def tenant_login(request):
    """Client access gateway: Sign up (new workspace) or Log in (existing user)."""
    slug = request.GET.get("instance") or request.session.get("active_tenant") or "softmarket"
    tenant = Tenant.objects.filter(slug=slug, active=True).first()
    if tenant and tenant.is_public:
        return redirect("crm:dashboard")
    return render(request, "crm/tenant_login.html", {
        "tenant": tenant, "active": "", "slug": slug,
    })


@require_GET
def client_access(request):
    """Always-on client gateway for the public 'Client login' link."""
    slug = request.session.get("active_tenant") or "softmarket"
    return render(request, "crm/tenant_login.html", {
        "tenant": None, "active": "", "slug": slug, "mode": request.GET.get("mode", "login"),
    })


@require_POST
def tenant_login_submit(request):
    """Branch on mode=signup|login. Both use real Django auth (per-user)."""
    from django.contrib.auth import authenticate, login
    from django.contrib.auth.models import User

    mode = request.POST.get("mode", "login")
    slug = (request.POST.get("instance") or request.session.get("active_tenant") or "softmarket").strip()

    if mode == "signup":
        business = (request.POST.get("business") or "").strip()
        email = (request.POST.get("email") or "").strip()
        password = (request.POST.get("password") or "").strip()
        if not business or not email or not password:
            return render(request, "crm/tenant_login.html", {
                "tenant": None, "slug": slug, "mode": "signup",
                "error": "Business name, email and password are required.",
            })
        if "@" not in email:
            return render(request, "crm/tenant_login.html", {
                "tenant": None, "slug": slug, "mode": "signup",
                "error": "Enter a valid email address.",
            })
        if User.objects.filter(username=email).exists():
            return render(request, "crm/tenant_login.html", {
                "tenant": None, "slug": slug, "mode": "signup",
                "error": "That email is already registered. Log in instead.",
            })
        # Create the user (username = email) + their private workspace.
        user = User.objects.create_user(username=email, email=email, password=password)
        tenant = services.create_workspace(business, email)
        TenantMembership.objects.create(user=user, tenant=tenant, role=TenantMembership.ROLE_OWNER)
        services.seed_demo_for_tenant(tenant, owner_name="Owner")
        login(request, user)
        request.session["active_tenant"] = tenant.slug
        request.session["show_tour"] = True
        return redirect("crm:dashboard")

    # mode == login
    email = (request.POST.get("email") or "").strip()
    password = (request.POST.get("password") or "").strip()
    user = authenticate(request, username=email, password=password)
    if user is None:
        return render(request, "crm/tenant_login.html", {
            "tenant": None, "active": "", "slug": slug, "mode": "login",
            "error": "Invalid email or password.",
        })
    membership = TenantMembership.objects.filter(user=user, tenant__active=True).first()
    if membership is None:
        return render(request, "crm/tenant_login.html", {
            "tenant": None, "active": "", "slug": slug, "mode": "login",
            "error": "No workspace linked to this account.",
        })
    login(request, user)
    request.session["active_tenant"] = membership.tenant.slug
    return redirect("crm:dashboard")


def tenant_logout(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect("crm:dashboard")


@require_POST
def clear_sample_data_view(request):
    """Bulk-clear the onboarding sample for the active tenant (owner-only)."""
    tenant = get_tenant(request)
    services.clear_sample_data(tenant)
    if is_htmx(request):
        return HttpResponse(status=204)
    return redirect("crm:dashboard")


def dismiss_tour(request):
    """Remember that this visitor dismissed the guided tour this session."""
    request.session["show_tour"] = False
    if is_htmx(request):
        return HttpResponse(status=204)
    return redirect("crm:dashboard")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def dashboard(request):
    tenant = get_tenant(request)
    contacts_count = Contact.objects.filter(tenant=tenant).count()
    open_pipeline = Opportunity.objects.filter(tenant=tenant).exclude(
        stage__in=[Opportunity.Stage.WON, Opportunity.Stage.LOST]
    )
    pipeline_value = sum(o.amount for o in open_pipeline)
    hot_leads = Lead.objects.filter(tenant=tenant, rating=Lead.Rating.HOT).count()
    tasks_due = Activity.objects.filter(
        tenant=tenant, type=Activity.Type.TASK, done=False
    ).count()
    recent_contacts = Contact.objects.filter(tenant=tenant)[:6]
    return render(request, "crm/dashboard.html", {
        "tenant": tenant,
        "active": "dashboard",
        "contacts_count": contacts_count,
        "pipeline_value": pipeline_value,
        "hot_leads": hot_leads,
        "tasks_due": tasks_due,
        "recent_contacts": recent_contacts,
        # What happened while nobody was logged in.
        "agent_runs": agent_runner.recent_runs(tenant, limit=4),
        "pending_suggestions": ledger.pending_suggestions(tenant).count(),
        "portfolio_trust": trust_service.portfolio_trust(tenant),
        "payments_summary": payments_service.payment_summary(tenant),
    })


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
def contact_list(request):
    tenant = get_tenant(request)
    q = request.GET.get("q", "").strip()
    qs = Contact.objects.filter(tenant=tenant)
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
        )
    ctx = {"tenant": tenant, "contacts": qs, "q": q}
    if is_htmx(request):
        return render(request, "crm/_contact_rows.html", ctx)
    return render(request, "crm/contact_list.html", ctx)


def contact_detail(request, pk):
    tenant = get_tenant(request)
    contact = get_object_or_404(Contact, tenant=tenant, pk=pk)
    return render(request, "crm/contact_detail.html", {
        "tenant": tenant,
        "contact": contact,
        "activities": contact.activities.all()[:50],
        "opportunities": contact.opportunities.all()[:50],
        # The Agent tab and the trust panel: what the agent did to this record,
        # and how much of the record still deserves belief.
        "agent_runs": agent_runner.runs_for_subject(tenant, Subject.CONTACT, contact.pk),
        "agent_upcoming": AgentTask.objects.filter(
            tenant=tenant, subject_type=Subject.CONTACT, subject_id=contact.pk,
            status=AgentTask.Status.QUEUED,
        ).order_by("due_at")[:5],
        "suggestions": Suggestion.objects.filter(
            tenant=tenant, subject_type=Subject.CONTACT, subject_id=contact.pk,
            status=Suggestion.Status.PENDING,
        ),
        "questions": AgentQuestion.objects.filter(
            tenant=tenant, subject_type=Subject.CONTACT, subject_id=contact.pk,
            status=AgentQuestion.Status.OPEN,
        ),
        "trust": trust_service.trust_report(contact, Subject.CONTACT),
        "payments": contact.payments.all()[:10],
    })


def contact_form(request, pk=None):
    tenant = get_tenant(request)
    contact = get_object_or_404(Contact, tenant=tenant, pk=pk) if pk else None
    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        form.fields["account"].queryset = Account.objects.filter(tenant=tenant)
        if form.is_valid():
            c = form.save(commit=False)
            c.tenant = tenant
            c.save()
            if is_htmx(request):
                return HttpResponse(headers={"HX-Redirect": c.get_absolute_url()})
            messages.success(request, f"Contact {c.full_name} saved.")
            return redirect("crm:contact_detail", pk=c.pk)
        # invalid: re-render the form partial so HTMX swaps errors in place
        if is_htmx(request):
            return render(request, "crm/_contact_form.html", {
                "tenant": tenant, "form": form, "contact": contact, "mode": "edit" if pk else "create",
            })
    else:
        form = ContactForm(instance=contact)
        form.fields["account"].queryset = Account.objects.filter(tenant=tenant)
    return render(request, "crm/contact_form.html", {
        "tenant": tenant, "form": form, "contact": contact,
        "mode": "edit" if pk else "create",
    })


@require_POST
def contact_delete(request, pk):
    tenant = get_tenant(request)
    contact = get_object_or_404(Contact, tenant=tenant, pk=pk)
    name = contact.full_name
    contact.delete()
    if is_htmx(request):
        return HttpResponse(headers={"HX-Redirect": "/crm/contacts/"})
    messages.success(request, f"Contact {name} deleted.")
    return redirect("crm:contact_list")


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def account_list(request):
    tenant = get_tenant(request)
    q = request.GET.get("q", "").strip()
    qs = Account.objects.filter(tenant=tenant)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(industry__icontains=q))
    ctx = {"tenant": tenant, "accounts": qs, "q": q}
    if is_htmx(request):
        return render(request, "crm/_account_rows.html", ctx)
    return render(request, "crm/account_list.html", ctx)


def account_detail(request, pk):
    tenant = get_tenant(request)
    account = get_object_or_404(Account, tenant=tenant, pk=pk)
    return render(request, "crm/account_detail.html", {
        "tenant": tenant,
        "account": account,
        "contacts": account.contacts.all(),
        "opportunities": account.opportunities.all(),
        "agent_runs": agent_runner.runs_for_subject(tenant, Subject.ACCOUNT, account.pk),
        "suggestions": Suggestion.objects.filter(
            tenant=tenant, subject_type=Subject.ACCOUNT, subject_id=account.pk,
            status=Suggestion.Status.PENDING,
        ),
        "trust": trust_service.trust_report(account, Subject.ACCOUNT),
    })


def account_form(request, pk=None):
    tenant = get_tenant(request)
    account = get_object_or_404(Account, tenant=tenant, pk=pk) if pk else None
    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            a = form.save(commit=False)
            a.tenant = tenant
            a.save()
            if is_htmx(request):
                return HttpResponse(headers={"HX-Redirect": a.get_absolute_url()})
            messages.success(request, f"Account {a.name} saved.")
            return redirect("crm:account_detail", pk=a.pk)
        if is_htmx(request):
            return render(request, "crm/_account_form.html", {
                "tenant": tenant, "form": form, "account": account, "mode": "edit" if pk else "create",
            })
    else:
        form = AccountForm(instance=account)
    return render(request, "crm/account_form.html", {
        "tenant": tenant, "form": form, "account": account,
        "mode": "edit" if pk else "create",
    })


@require_POST
def account_delete(request, pk):
    tenant = get_tenant(request)
    account = get_object_or_404(Account, tenant=tenant, pk=pk)
    name = account.name
    account.delete()
    if is_htmx(request):
        return HttpResponse(headers={"HX-Redirect": "/crm/accounts/"})
    messages.success(request, f"Account {name} deleted.")
    return redirect("crm:account_list")


# ---------------------------------------------------------------------------
# Activities (Milestone 2 — 360 timeline log + task toggle)
# ---------------------------------------------------------------------------
def activity_create(request, contact_pk):
    tenant = get_tenant(request)
    contact = get_object_or_404(Contact, tenant=tenant, pk=contact_pk)
    if request.method == "POST":
        form = ActivityForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.tenant = tenant
            a.contact = contact
            a.save()
            if is_htmx(request):
                return HttpResponse(headers={"HX-Redirect": contact.get_absolute_url()})
            messages.success(request, "Activity logged.")
            return redirect("crm:contact_detail", pk=contact.pk)
        if is_htmx(request):
            return render(request, "crm/_activity_form.html", {
                "tenant": tenant, "form": form, "contact": contact,
            })
    else:
        form = ActivityForm(initial={"type": Activity.Type.NOTE})
    return render(request, "crm/_activity_form.html", {
        "tenant": tenant, "form": form, "contact": contact,
    })


@require_POST
def activity_toggle(request, pk):
    """HTMX toggle of a task's `done` checkbox — swaps just the timeline row."""
    tenant = get_tenant(request)
    activity = get_object_or_404(Activity, tenant=tenant, pk=pk)
    activity.done = not activity.done
    activity.save(update_fields=["done"])
    return render(request, "crm/_activity_row.html", {"activity": activity, "tenant": tenant})


# ---------------------------------------------------------------------------
# Pipeline (Milestone 4 — Kanban board + list + drag-to-move)
# M6: stages come from the tenant's TenantStage config (services.tenant_stages),
# so each white-label instance renders its own branded pipeline.
# ---------------------------------------------------------------------------
def _stage_summary(tenant):
    """Per-stage open value + weighted forecast, reused by board + API."""
    stages = services.tenant_stages(tenant)
    open_value = 0
    weighted = 0
    won_value = 0
    lost_value = 0
    by_stage = []
    for ts in stages:
        opps = list(Opportunity.objects.filter(tenant=tenant, stage=ts.key))
        value = sum(o.amount for o in opps)
        if ts.is_won:
            won_value = value
        elif ts.is_lost:
            lost_value = value
        else:
            open_value += value
            weighted += round(value * (ts.probability or 0) / 100)
        by_stage.append({
            "stage": ts.key,
            "stage_label": ts.label,
            "count": len(opps),
            "value": value,
        })
    return {
        "open_value": open_value,
        "weighted": weighted,
        "won_value": won_value,
        "lost_value": lost_value,
        "by_stage": by_stage,
    }


def _board_columns(tenant):
    stages = services.tenant_stages(tenant)
    columns = []
    for ts in stages:
        opps = list(Opportunity.objects.filter(tenant=tenant, stage=ts.key).order_by("order", "-created_at"))
        columns.append({
            "stage": ts.key,
            "stage_label": ts.label,
            "is_won": ts.is_won,
            "is_lost": ts.is_lost,
            "opps": opps,
            "value": sum(o.amount for o in opps),
            "count": len(opps),
        })
    return columns


def pipeline_board(request):
    tenant = get_tenant(request)
    summary = _stage_summary(tenant)
    columns = _board_columns(tenant)
    ctx = {"tenant": tenant, "active": "pipeline", "columns": columns, "summary": summary}
    if is_htmx(request):
        return render(request, "crm/_pipeline_columns.html", ctx)
    return render(request, "crm/pipeline_board.html", ctx)


def pipeline_list(request):
    tenant = get_tenant(request)
    opps = Opportunity.objects.filter(tenant=tenant).order_by("stage", "order", "-created_at")
    summary = _stage_summary(tenant)
    return render(request, "crm/pipeline_list.html", {
        "tenant": tenant, "active": "pipeline", "opps": opps, "summary": summary,
    })


@require_POST
def opportunity_move(request, pk):
    """HTMX endpoint: move a deal to a new stage (+ optional new order).

    Called on drag-drop. Persists stage/order, then swaps the board columns and
    the forecast header in place so totals + weighted forecast update live.
    """
    tenant = get_tenant(request)
    opp = get_object_or_404(Opportunity, tenant=tenant, pk=pk)
    new_stage = request.POST.get("stage")
    valid_stages = {s.key for s in services.tenant_stages(tenant)}
    if new_stage in valid_stages:
        opp.stage = new_stage
    # Reorder: caller may pass an ordered list of ids for the destination column.
    order_ids = request.POST.getlist("order")
    if order_ids:
        for idx, oid in enumerate(order_ids):
            try:
                target = Opportunity.objects.get(tenant=tenant, pk=int(oid))
                target.order = idx
                target.save(update_fields=["order"])
            except (ValueError, Opportunity.DoesNotExist):
                pass
    opp.save(update_fields=["stage", "updated_at"])
    if is_htmx(request):
        summary = _stage_summary(tenant)
        columns = _board_columns(tenant)
        return render(request, "crm/_pipeline_columns.html",
                      {"tenant": tenant, "columns": columns, "summary": summary})
    return redirect("crm:pipeline_board")


# ---------------------------------------------------------------------------
# Follow-ups + churn (Milestone 5 — to-do list, check-off, churn radar)
# ---------------------------------------------------------------------------
def followups(request):
    """Rep's daily to-do: open follow-up tasks bucketed by due date, plus the
    churn radar (customers gone quiet)."""
    tenant = get_tenant(request)
    buckets = services.followup_buckets(tenant)
    churn = services.churn_candidates(tenant)
    return render(request, "crm/followups.html", {
        "tenant": tenant, "active": "followups",
        "buckets": buckets, "churn": churn,
        "churn_days": services.CHURN_THRESHOLD_DAYS,
    })


@require_POST
def followup_toggle(request, pk):
    """Check off (or re-open) a follow-up task from the to-do list. HTMX swaps
    the whole to-do panel so bucket counts + churn stay in sync."""
    tenant = get_tenant(request)
    activity = get_object_or_404(Activity, tenant=tenant, pk=pk)
    activity.done = not activity.done
    activity.save(update_fields=["done"])
    if is_htmx(request):
        buckets = services.followup_buckets(tenant)
        churn = services.churn_candidates(tenant)
        return render(request, "crm/_followup_panel.html", {
            "tenant": tenant, "buckets": buckets, "churn": churn,
            "churn_days": services.CHURN_THRESHOLD_DAYS,
        })
    return redirect("crm:followups")


@require_POST
def contact_lifecycle(request, pk):
    """Transition a contact's lifecycle stage (e.g. reactivate a churned
    customer, or mark churned). Logs the change to the 360 timeline."""
    tenant = get_tenant(request)
    contact = get_object_or_404(Contact, tenant=tenant, pk=pk)
    services.set_lifecycle(contact, request.POST.get("lifecycle", ""))
    if is_htmx(request):
        return HttpResponse(headers={"HX-Redirect": contact.get_absolute_url()})
    messages.success(request, f"{contact.full_name} moved to {contact.get_lifecycle_display()}.")
    return redirect("crm:contact_detail", pk=contact.pk)


# ---------------------------------------------------------------------------
# White-label config (Milestone 6 — branding, stages, integrations)
# ---------------------------------------------------------------------------
@require_GET
def crm_settings(request):
    tenant = get_tenant(request)
    stages = services.tenant_stages(tenant)
    integrations = IntegrationConfig.objects.filter(tenant=tenant).order_by("channel")
    queue = IntegrationMessage.objects.filter(tenant=tenant).order_by("-created_at")[:20]
    return render(request, "crm/settings.html", {
        "tenant": tenant,
        "active": "settings",
        "stages": stages,
        "integrations": integrations,
        "queue": queue,
    })


@require_POST
def crm_settings_save(request):
    """Persist branding colors/logo + per-tenant pipeline stages + integration toggles."""
    tenant = get_tenant(request)
    tenant.brand_primary_color = request.POST.get("brand_primary_color", tenant.brand_primary_color)
    tenant.brand_accent_color = request.POST.get("brand_accent_color", tenant.brand_accent_color)
    tenant.logo_url = request.POST.get("logo_url", tenant.logo_url)
    tenant.name = request.POST.get("name", tenant.name)
    tenant.save(update_fields=["name", "brand_primary_color", "brand_accent_color", "logo_url", "updated_at"])

    # Upsert pipeline stages from the form (keys are stable; labels/prob/order editable).
    seen = set()
    i = 0
    while True:
        key = request.POST.get(f"stage_key_{i}")
        if not key:
            break
        label = request.POST.get(f"stage_label_{i}", key)
        prob = int(request.POST.get(f"stage_prob_{i}", 50) or 50)
        is_won = request.POST.get(f"stage_won_{i}") == "on"
        is_lost = request.POST.get(f"stage_lost_{i}") == "on"
        TenantStage.objects.update_or_create(
            tenant=tenant, key=key,
            defaults={"label": label, "order": i, "probability": prob,
                      "is_won": is_won, "is_lost": is_lost},
        )
        seen.add(key)
        i += 1
    TenantStage.objects.filter(tenant=tenant).exclude(key__in=seen).delete()

    # Integration toggles.
    for ch in services.INTEGRATION_CHANNELS:
        enabled = request.POST.get(f"integration_{ch}") == "on"
        IntegrationConfig.objects.update_or_create(
            tenant=tenant, channel=ch, defaults={"enabled": enabled}
        )
    return redirect("crm:crm_settings")


@require_POST
def integration_send(request):
    """Demo enqueue: prove the outbound queue path for a channel (no live call)."""
    tenant = get_tenant(request)
    channel = request.POST.get("channel")
    recipient = request.POST.get("recipient", "")
    if channel in services.INTEGRATION_CHANNELS:
        msg = services.enqueue_integration_message(tenant, channel, recipient,
                                                    payload={"demo": True})
        return JsonResponse({"ok": True, "id": msg.id, "status": msg.status})
    return JsonResponse({"ok": False, "error": "unknown channel"}, status=400)


# ---------------------------------------------------------------------------
# Leads (Milestone 3 — public intake + front office)
# ---------------------------------------------------------------------------
def lead_intake(request):
    """Public web-intake form (no auth). On submit: score BANT, auto-assign
    owner by territory, and send the triggered auto-response email."""
    slug = request.GET.get("instance") or "softmarket"
    tenant = Tenant.objects.filter(slug=slug, active=True).first()
    if not tenant:
        raise Http404("CRM instance not found.")
    if request.method == "POST":
        form = PublicLeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.tenant = tenant
            lead.save()
            services.intake_lead(lead)
            if is_htmx(request):
                return render(request, "crm/_lead_thanks.html", {"lead": lead})
            return render(request, "crm/lead_thanks.html", {"tenant": tenant, "lead": lead})
        if is_htmx(request):
            return render(request, "crm/_lead_form.html", {"tenant": tenant, "form": form})
    else:
        form = PublicLeadForm(initial={"source": Lead.Source.WEB_FORM})
    return render(request, "crm/lead_form.html", {"tenant": tenant, "form": form})


def lead_list(request):
    tenant = get_tenant(request)
    rating = request.GET.get("rating")
    qs = Lead.objects.filter(tenant=tenant)
    if rating:
        qs = qs.filter(rating=rating)
    return render(request, "crm/lead_list.html", {
        "tenant": tenant, "leads": qs, "rating_filter": rating or "",
    })


def lead_detail(request, pk):
    tenant = get_tenant(request)
    lead = get_object_or_404(Lead, tenant=tenant, pk=pk)
    return render(request, "crm/lead_detail.html", {"tenant": tenant, "lead": lead})


@require_POST
def lead_convert(request, pk):
    """Promote a lead into a Contact (the 360 hub). HTMX swaps the badge."""
    tenant = get_tenant(request)
    lead = get_object_or_404(Lead, tenant=tenant, pk=pk)
    contact = services.convert_lead_to_contact(lead, create_account=True)
    if is_htmx(request):
        return render(request, "crm/_lead_status.html", {"lead": lead, "contact": contact})
    messages.success(request, f"Lead converted to {contact.full_name}.")
    return redirect("crm:contact_detail", pk=contact.pk)


# ---------------------------------------------------------------------------
# M7 — the agent console
#
# Three things a rep needs from an autonomous colleague: what did you change,
# what are you asking me, and what are you about to do next.
# ---------------------------------------------------------------------------
def agent_inbox(request):
    tenant = get_tenant(request)
    return render(request, "crm/agent_inbox.html", {
        "tenant": tenant,
        "active": "agent",
        "suggestions": ledger.pending_suggestions(tenant).order_by("-confidence", "-created_at"),
        "questions": AgentQuestion.objects.filter(
            tenant=tenant, status=AgentQuestion.Status.OPEN
        ),
        "runs": agent_runner.recent_runs(tenant, limit=15),
        "upcoming": agent_queue.upcoming(tenant, limit=15),
        "depth": agent_queue.queue_depth(tenant),
        "planner": _planner_name(),
    })


def _planner_name():
    """Which planner will actually run — say so rather than implying an LLM."""
    from django.conf import settings

    from .agent import brain

    use_llm = getattr(settings, "CRM_AGENT_USE_LLM", True)
    return "claude" if use_llm and brain.is_configured() else "playbook"


@require_POST
def suggestion_decide(request, pk):
    """Accept or reject one proposed change."""
    tenant = get_tenant(request)
    suggestion = get_object_or_404(Suggestion, tenant=tenant, pk=pk)
    decision = request.POST.get("decision", "")
    who = request.POST.get("by", "") or (
        request.user.get_username() if request.user.is_authenticated else "front office"
    )
    if decision == "accept":
        ledger.accept_suggestion(suggestion, decided_by=who)
    elif decision == "reject":
        ledger.reject_suggestion(suggestion, decided_by=who)
    if is_htmx(request):
        return render(request, "crm/_suggestion_row.html",
                      {"tenant": tenant, "suggestion": suggestion})
    return redirect("crm:agent_inbox")


@require_POST
def question_answer(request, pk):
    tenant = get_tenant(request)
    question = get_object_or_404(AgentQuestion, tenant=tenant, pk=pk)
    answer = request.POST.get("answer", "").strip()
    if answer:
        question.answer = answer
        question.status = AgentQuestion.Status.ANSWERED
        from django.utils import timezone

        question.answered_at = timezone.now()
        question.save(update_fields=["answer", "status", "answered_at", "updated_at"])
    if is_htmx(request):
        return render(request, "crm/_question_row.html",
                      {"tenant": tenant, "question": question})
    return redirect("crm:agent_inbox")


@require_POST
def agent_run_now(request):
    """'Ask the agent' — queue a task for a record and run it immediately."""
    tenant = get_tenant(request)
    subject_type = request.POST.get("subject_type", Subject.CONTACT)
    subject_id = int(request.POST.get("subject_id", 0) or 0)
    kind = request.POST.get("kind") or {
        Subject.CONTACT: AgentTask.Kind.RESEARCH_CONTACT,
        Subject.ACCOUNT: AgentTask.Kind.ENRICH_ACCOUNT,
        Subject.OPPORTUNITY: AgentTask.Kind.REVIEW_DEAL,
    }.get(subject_type, AgentTask.Kind.BRIEF)
    run = agent_runner.run_now(
        tenant, kind, subject_type, subject_id,
        reason=request.POST.get("reason", "A rep asked for a look."),
    )
    if is_htmx(request):
        return render(request, "crm/_agent_runs.html", {
            "tenant": tenant,
            "agent_runs": agent_runner.runs_for_subject(tenant, subject_type, subject_id),
            "subject_type": subject_type,
            "subject_id": subject_id,
        })
    messages.success(request, run.brief or "The agent found nothing to change.")
    return redirect(request.POST.get("next", "/crm/agent/"))


@require_POST
def agent_sweep(request):
    """Queue tonight's work now — decayed records, open deals, unseen contacts."""
    tenant = get_tenant(request)
    queued = agent_runner.sweep(tenant)
    messages.success(request, f"Queued {len(queued)} task(s) for the agent.")
    return redirect("crm:agent_inbox")


# ---------------------------------------------------------------------------
# Bonus 1 — data trust score + decay radar
# ---------------------------------------------------------------------------
def trust_dashboard(request):
    tenant = get_tenant(request)
    return render(request, "crm/trust.html", {
        "tenant": tenant,
        "active": "trust",
        "portfolio": trust_service.portfolio_trust(tenant),
        "radar": trust_service.decay_radar(tenant, limit=25),
        "recent": trust_service.recently_verified(tenant, days=14, limit=15),
    })


@require_POST
def trust_queue_verification(request):
    tenant = get_tenant(request)
    queued = trust_service.queue_reverification(tenant, limit=15, threshold=55)
    messages.success(
        request, f"Asked the agent to re-verify {len(queued)} record(s)."
    )
    return redirect("crm:trust_dashboard")


# ---------------------------------------------------------------------------
# Bonus 2 — payments-aware pipeline
# ---------------------------------------------------------------------------
def payments_console(request):
    tenant = get_tenant(request)
    return render(request, "crm/payments.html", {
        "tenant": tenant,
        "active": "payments",
        "summary": payments_service.payment_summary(tenant),
        "payments": PaymentEvent.objects.filter(tenant=tenant).select_related(
            "contact", "opportunity"
        )[:50],
    })


@require_POST
def payment_ingest(request):
    """Paste an M-Pesa confirmation. Parsing and matching happen on save."""
    tenant = get_tenant(request)
    text = request.POST.get("text", "").strip()
    if not text:
        messages.error(request, "Paste the confirmation message first.")
        return redirect("crm:payments_console")
    payment = payments_service.record_payment(tenant, text=text)
    if payment.status == PaymentEvent.Status.MATCHED:
        messages.success(
            request,
            f"KSh {payment.amount:,.0f} matched to {payment.opportunity.name} — "
            f"{payment.match_reason}",
        )
    else:
        messages.success(
            request, f"Recorded KSh {payment.amount:,.0f}. {payment.match_reason}"
        )
    return redirect("crm:payments_console")


@require_POST
def payment_resolve(request, pk):
    """A human settles an ambiguous payment against a specific deal."""
    tenant = get_tenant(request)
    payment = get_object_or_404(PaymentEvent, tenant=tenant, pk=pk)
    opportunity_id = request.POST.get("opportunity")
    if request.POST.get("decision") == "ignore":
        payment.status = PaymentEvent.Status.IGNORED
        payment.save(update_fields=["status", "updated_at"])
        messages.success(request, "Payment set aside.")
        return redirect("crm:payments_console")
    opportunity = get_object_or_404(Opportunity, tenant=tenant, pk=opportunity_id)
    contact = payment.contact or opportunity.contact
    payments_service.apply_match(
        payment, contact, opportunity, 100,
        "Attributed by a person from the review queue.",
        decided_by=request.POST.get("by", "front office"),
    )
    messages.success(request, f"Booked against {opportunity.name}.")
    return redirect("crm:payments_console")


@csrf_exempt
@require_POST
def mpesa_confirmation(request):
    """Daraja C2B confirmation endpoint.

    CSRF-exempt because Safaricom posts server-to-server with no session. The
    endpoint is idempotent on the transaction code, so a retried callback — of
    which Daraja sends plenty — cannot double-count revenue.
    """
    tenant = resolve_tenant(request)
    if not tenant:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Unknown instance"}, status=404)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Malformed payload"}, status=400)
    payment = payments_service.record_payment(tenant, payload=payload)
    # Safaricom retries anything that is not an explicit success.
    return JsonResponse({
        "ResultCode": 0,
        "ResultDesc": "Accepted",
        "crm": {"payment_id": payment.id, "status": payment.status},
    })


# ---------------------------------------------------------------------------
# Bonus 3 — the client-facing deal room
# ---------------------------------------------------------------------------
def deal_rooms(request):
    tenant = get_tenant(request)
    rooms = DealRoom.objects.filter(tenant=tenant).select_related("opportunity")
    rows = []
    for room in rooms:
        state, label = dealroom_service.engagement_label(room)
        rows.append({"room": room, "state": state, "label": label,
                     **dealroom_service.engagement(room)})
    return render(request, "crm/deal_rooms.html", {
        "tenant": tenant,
        "active": "rooms",
        "rows": rows,
        "attention": dealroom_service.rooms_needing_attention(tenant),
        "openable": Opportunity.objects.filter(tenant=tenant, deal_room__isnull=True)[:50],
    })


@require_POST
def deal_room_create(request, opportunity_pk):
    tenant = get_tenant(request)
    opportunity = get_object_or_404(Opportunity, tenant=tenant, pk=opportunity_pk)
    room = dealroom_service.ensure_room(opportunity)
    messages.success(request, f"Deal room ready — share {room.get_absolute_url()}")
    return redirect("crm:deal_rooms")


@require_POST
def deal_room_toggle(request, pk):
    tenant = get_tenant(request)
    room = get_object_or_404(DealRoom, tenant=tenant, pk=pk)
    room.active = not room.active
    room.save(update_fields=["active", "updated_at"])
    messages.success(request, "Deal room " + ("re-opened." if room.active else "closed."))
    return redirect("crm:deal_rooms")


def deal_room_public(request, token):
    """The buyer's view. No auth — the token is the credential."""
    from django.utils import timezone

    room = DealRoom.objects.filter(token=token, active=True).select_related(
        "opportunity", "opportunity__contact", "tenant"
    ).first()
    if room is None or (room.expires_at and room.expires_at < timezone.now()):
        raise Http404("This link is no longer active.")
    dealroom_service.log_view(room, request)
    return render(request, "crm/deal_room_public.html", {
        "tenant": room.tenant,
        "room": room,
        "opportunity": room.opportunity,
        "payment": dealroom_service.payment_instructions(room.tenant),
        "total": room.total,
    })


@require_POST
def deal_room_accept(request, token):
    room = get_object_or_404(DealRoom, token=token, active=True)
    dealroom_service.accept(
        room,
        name=request.POST.get("name", ""),
        note=request.POST.get("note", ""),
    )
    return render(request, "crm/deal_room_public.html", {
        "tenant": room.tenant,
        "room": room,
        "opportunity": room.opportunity,
        "payment": dealroom_service.payment_instructions(room.tenant),
        "total": room.total,
        "just_accepted": True,
    })
