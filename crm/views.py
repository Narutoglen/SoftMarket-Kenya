"""Server-rendered front office for the white-label CRM core (Milestone 1).

Stack: Django + Tailwind + HTMX (per the PRD). HTMX requests are detected via
the `HX-Request` header — list/delete views return partials or an
`HX-Redirect`, while plain requests get the full page.
"""

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import services
from .api import resolve_tenant
from .forms import AccountForm, ActivityForm, ContactForm, PublicLeadForm
from .models import (
    Account,
    Activity,
    Contact,
    IntegrationConfig,
    IntegrationMessage,
    Lead,
    Opportunity,
    Tenant,
    TenantStage,
)


def get_tenant(request):
    tenant = resolve_tenant(request)
    if not tenant:
        raise Http404("CRM instance not found.")
    return tenant


def is_htmx(request):
    return request.headers.get("HX-Request") == "true"


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
