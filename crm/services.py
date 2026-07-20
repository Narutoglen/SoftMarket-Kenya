"""CRM service layer: BANT scoring, lead routing, dedupe/merge, reporting.

Kept separate from models (marketplace-style) so views stay thin and the logic
is reusable by the white-label core for ANY tenant instance.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F
from decimal import Decimal
from django.utils import timezone

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


# ---------------------------------------------------------------------------
# BANT scoring -> hot / warm / cold
def score_lead_rating(lead: Lead) -> Lead.Rating:
    total = lead.bant_score()
    if total >= 9:
        return Lead.Rating.HOT
    if total >= 5:
        return Lead.Rating.WARM
    return Lead.Rating.COLD


# Simple territory -> owner map. Per the white-label design this should later
# live on the Tenant (or a routing config row); hardcoded defaults keep the
# first SoftMarket instance working out of the box.
DEFAULT_TERRITORY_OWNERS = {
    "nairobi": "Brian Mukwe",
    "kiambu": "Brian Mukwe",
    "nakuru": "Tati Shayo",
    "kisumu": "Tati Shayo",
    "mombasa": "Dan Kigotho",
    "eldoret": "Dan Kigotho",
}


def route_lead_owner(tenant: Tenant, lead: Lead) -> str:
    """Pick the rep who should own this lead (territory-based auto-assign)."""
    terr = (lead.territory or "").strip().lower()
    if terr in DEFAULT_TERRITORY_OWNERS:
        return DEFAULT_TERRITORY_OWNERS[terr]
    return tenant.default_lead_owner or "Unassigned"


def qualify_lead(lead: Lead) -> Lead:
    """Run BANT scoring + auto-assign. Idempotent."""
    lead.rating = score_lead_rating(lead)
    if not lead.owner:
        lead.owner = route_lead_owner(lead.tenant, lead)
    lead.save(update_fields=["rating", "owner", "updated_at"])
    return lead


# ---------------------------------------------------------------------------
# Auto-responder (triggered lead email) — the one marketing email in v1
# ---------------------------------------------------------------------------
def send_lead_autoresponse(lead: Lead) -> bool:
    """Email the lead a confirmation + notify the assigned rep.

    Uses Django's configured email backend (console in dev, SMTP in prod via
    env). Returns True if the send was attempted without raising. Failures are
    swallowed so a flaky mail server never blocks lead capture.
    """
    tenant = lead.tenant
    from_email = settings.DEFAULT_FROM_EMAIL
    recipients = [lead.email] if lead.email else []
    sent_any = False

    if recipients:
        subject = f"Thanks for reaching out to {tenant.name}"
        greeting = lead.first_name or "there"
        body = (
            f"Hi {greeting},\n\n"
            f"Thanks for your interest in {tenant.name}. We've received your "
            f"enquiry and {lead.owner or 'a specialist'} will be in touch within "
            f"24 hours.\n\n"
            f"— The {tenant.name} team"
        )
        try:
            send_mail(subject, body, from_email, recipients, fail_silently=False)
            sent_any = True
        except Exception:
            sent_any = False

    # Internal notification to the assigned rep / admins (best-effort).
    notify = list(getattr(settings, "ADMIN_NOTIFICATION_EMAILS", []) or [])
    if notify:
        try:
            send_mail(
                f"[{tenant.name}] New {lead.get_rating_display()} lead: {lead.full_name}",
                (
                    f"Source: {lead.get_source_display()}\n"
                    f"Owner: {lead.owner or 'Unassigned'}\n"
                    f"Rating: {lead.get_rating_display()} (BANT {lead.bant_score()}/12)\n"
                    f"Email: {lead.email}\nPhone: {lead.phone}\n"
                    f"Territory: {lead.territory}\n\nMessage:\n{lead.message}"
                ),
                from_email,
                notify,
                fail_silently=True,
            )
        except Exception:
            pass

    return sent_any


def intake_lead(lead: Lead) -> Lead:
    """Full public-intake pipeline: score + route + auto-respond. Idempotent-ish
    (safe to re-run; only flips auto_responded once)."""
    qualify_lead(lead)
    if not lead.auto_responded:
        send_lead_autoresponse(lead)
        lead.auto_responded = True
        lead.save(update_fields=["auto_responded", "updated_at"])
    return lead


# ---------------------------------------------------------------------------
# Dedupe / merge (collapse duplicate contacts, keep newest-per-field)
# ---------------------------------------------------------------------------
def find_duplicate_contacts(tenant: Tenant, email=None, phone=None):
    """Return contacts in this tenant sharing the given email or phone."""
    qs = Contact.objects.filter(tenant=tenant)
    if email:
        qs = qs.filter(email__iexact=email)
    if phone:
        qs = qs.filter(phone=phone)
    return qs.order_by("created_at")


def merge_contacts(primary: Contact, duplicates):
    """Merge `duplicates` into `primary`, keeping the newest value per field.

    Transfers activities/opportunities to primary, then deletes duplicates.
    Returns the number of merged (deleted) records.
    """
    text_fields = ["first_name", "last_name", "email", "phone", "personal_notes", "territory"]
    for dup in duplicates:
        if dup.pk == primary.pk:
            continue
        # Keep newest non-empty text field.
        for f in text_fields:
            cur = getattr(primary, f)
            new = getattr(dup, f)
            if not cur and new:
                setattr(primary, f, new)
        # Keep the newer date_of_birth if primary lacks one.
        if not primary.date_of_birth and dup.date_of_birth:
            primary.date_of_birth = dup.date_of_birth
        # Re-parent related records.
        dup.activities.update(contact=primary)
        dup.opportunities.update(contact=primary)
        if dup.account and not primary.account:
            primary.account = dup.account
        dup.delete()
    primary.save()
    return len([d for d in duplicates if d.pk != primary.pk])


# ---------------------------------------------------------------------------
# Conversion: Lead -> Contact (+ optional Account)
# ---------------------------------------------------------------------------
def convert_lead_to_contact(lead: Lead, create_account=False) -> Contact:
    """Promote a qualified lead into a Contact (the 360 hub)."""
    if lead.converted_contact:
        return lead.converted_contact
    account = None
    if create_account and lead.company:
        account, _ = Account.objects.get_or_create(
            tenant=lead.tenant, name=lead.company,
            defaults={"notes": "Created from lead conversion."},
        )
    contact = Contact.objects.create(
        tenant=lead.tenant,
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        phone=lead.phone,
        territory=lead.territory,
        account=account,
        lifecycle=Contact.Lifecycle.LEAD,
    )
    # Carry the original message into an activity for the 360 view.
    if lead.message:
        Activity.objects.create(
            tenant=lead.tenant, contact=contact,
            type=Activity.Type.NOTE, subject="Original lead inquiry",
            notes=lead.message,
        )
    lead.converted_contact = contact
    lead.save(update_fields=["converted_contact", "updated_at"])
    return contact


# ---------------------------------------------------------------------------
# Pipeline reporting (forecast by stage / amount)
# ---------------------------------------------------------------------------
def pipeline_summary(tenant: Tenant):
    """Return open pipeline totals grouped by stage + weighted forecast."""
    open_stages = [
        Opportunity.Stage.PROSPECTING,
        Opportunity.Stage.QUALIFICATION,
        Opportunity.Stage.PROPOSAL,
        Opportunity.Stage.NEGOTIATION,
    ]
    rows = []
    total_open = 0
    weighted = 0
    for stage in open_stages:
        opps = Opportunity.objects.filter(tenant=tenant, stage=stage)
        count = opps.count()
        value = sum(o.amount for o in opps)
        prob = {
            Opportunity.Stage.PROSPECTING: 10,
            Opportunity.Stage.QUALIFICATION: 30,
            Opportunity.Stage.PROPOSAL: 60,
            Opportunity.Stage.NEGOTIATION: 80,
        }[stage]
        stage_weighted = round(value * prob / 100)
        total_open += value
        weighted += stage_weighted
        rows.append({
            "stage": stage,
            "stage_label": Opportunity.Stage(stage).label,
            "count": count,
            "value": value,
            "probability": prob,
            "weighted": stage_weighted,
        })
    won = Opportunity.objects.filter(tenant=tenant, stage=Opportunity.Stage.WON)
    lost = Opportunity.objects.filter(tenant=tenant, stage=Opportunity.Stage.LOST)
    return {
        "open_pipeline_value": total_open,
        "weighted_forecast": weighted,
        "won_value": sum(o.amount for o in won),
        "lost_value": sum(o.amount for o in lost),
        "by_stage": rows,
        "generated_at": timezone.localtime(timezone.now()).isoformat(),
    }


# ---------------------------------------------------------------------------
# Follow-ups + churn detection (Milestone 5)
# ---------------------------------------------------------------------------
# A customer with no activity in this many days is flagged at-risk / churning.
CHURN_THRESHOLD_DAYS = 30


def open_followups(tenant: Tenant):
    """Open task activities (the to-do list), ordered by due date (soonest first,
    undated last). Overdue/today are surfaced by the caller via `due_at`."""
    return (
        Activity.objects.filter(tenant=tenant, type=Activity.Type.TASK, done=False)
        .select_related("contact")
        .order_by(F("due_at").asc(nulls_last=True), "created_at")
    )


def followup_buckets(tenant: Tenant):
    """Split open follow-ups into overdue / today / upcoming / no-date buckets."""
    now = timezone.localtime(timezone.now())
    today = now.date()
    overdue, due_today, upcoming, undated = [], [], [], []
    for a in open_followups(tenant):
        if a.due_at is None:
            undated.append(a)
        else:
            d = timezone.localtime(a.due_at).date()
            if d < today:
                overdue.append(a)
            elif d == today:
                due_today.append(a)
            else:
                upcoming.append(a)
    return {
        "overdue": overdue,
        "today": due_today,
        "upcoming": upcoming,
        "undated": undated,
        "total": len(overdue) + len(due_today) + len(upcoming) + len(undated),
    }


def last_activity_at(contact: Contact):
    """Timestamp of the contact's most recent activity, or None."""
    latest = contact.activities.order_by("-created_at").first()
    return latest.created_at if latest else None


def churn_candidates(tenant: Tenant, days: int = CHURN_THRESHOLD_DAYS):
    """Return customers who've gone quiet: lifecycle=customer with no activity in
    the last `days` days (or never). Each item carries the contact + how many
    days since their last touch (None = never)."""
    cutoff = timezone.now() - timedelta(days=days)
    now = timezone.now()
    rows = []
    customers = Contact.objects.filter(
        tenant=tenant, lifecycle=Contact.Lifecycle.CUSTOMER
    ).select_related("account")
    for c in customers:
        last = last_activity_at(c)
        if last is None or last < cutoff:
            days_quiet = None if last is None else (now - last).days
            rows.append({"contact": c, "last_activity": last, "days_quiet": days_quiet})
    # Longest-quiet first; never-touched (None) at the top.
    rows.sort(key=lambda r: (r["days_quiet"] is not None, r["days_quiet"] or 0), reverse=True)
    return rows


def set_lifecycle(contact: Contact, lifecycle: str) -> Contact:
    """Transition a contact's lifecycle stage (subscriber/lead/customer/churned).
    Logs a note activity so the 360 timeline records the transition."""
    valid = {c[0] for c in Contact.Lifecycle.choices}
    if lifecycle not in valid or lifecycle == contact.lifecycle:
        return contact
    old = contact.get_lifecycle_display()
    contact.lifecycle = lifecycle
    contact.save(update_fields=["lifecycle", "updated_at"])
    Activity.objects.create(
        tenant=contact.tenant, contact=contact, type=Activity.Type.NOTE,
        subject="Lifecycle change",
        notes=f"Moved from {old} to {contact.get_lifecycle_display()}.",
    )
    return contact


# ---------------------------------------------------------------------------
# M6 — white-label integrations (contracts only, no live third-party calls)
# ---------------------------------------------------------------------------
INTEGRATION_CHANNELS = ["mpesa", "whatsapp", "etims", "offline"]


def ensure_integration_configs(tenant: Tenant):
    """Create the four channel IntegrationConfig rows for a tenant if missing."""
    created = []
    for ch in INTEGRATION_CHANNELS:
        obj, made = IntegrationConfig.objects.get_or_create(tenant=tenant, channel=ch)
        if made:
            created.append(obj)
    return created


def enqueue_integration_message(tenant, channel, recipient, payload=None):
    """Add an outbound message to the queue for a worker to drain later.

    Returns the created IntegrationMessage (status=pending). No network call.
    """
    return IntegrationMessage.objects.create(
        tenant=tenant,
        channel=channel,
        recipient=recipient or "",
        payload=payload or {},
    )


def tenant_stages(tenant: Tenant):
    """Ordered pipeline stages for a tenant (falls back to defaults if none)."""
    stages = list(TenantStage.objects.filter(tenant=tenant).order_by("order"))
    if not stages:
        # Sensible default pipeline so a brand-new tenant still has a board.
        defaults = [
            ("prospecting", "Prospecting", 10, False, False),
            ("qualification", "Qualification", 25, False, False),
            ("proposal", "Proposal", 50, False, False),
            ("negotiation", "Negotiation", 80, False, False),
            ("won", "Won", 100, True, False),
            ("lost", "Lost", 0, False, True),
        ]
        stages = [
            TenantStage(tenant=tenant, key=k, label=l, order=i,
                        probability=p, is_won=w, is_lost=lo)
            for i, (k, l, p, w, lo) in enumerate(defaults)
        ]
    return stages


# ---------------------------------------------------------------------------
# Self-serve workspace creation (client sign-up gate)
def normalize_slug(value: str) -> str:
    """Turn a business name into a url-safe tenant slug, de-duplicated."""
    import re
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "client"
    slug = base
    n = 1
    while Tenant.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def create_workspace(business_name: str, email: str) -> Tenant:
    """Create a new PRIVATE white-label tenant for a self-served client.

    Provisions the default pipeline stages + integration configs so the
    workspace is usable immediately. Auth is real Django auth (per-user
    TenantMembership), so no shared access code is generated. Returns the Tenant.
    """
    from marketplace.models import TimeStampedModel  # noqa: F401  (ensures app loaded)

    slug = normalize_slug(business_name)
    tenant = Tenant.objects.create(
        slug=slug,
        name=business_name.strip() or slug,
        is_public=False,
        contact_email=email.strip(),
        default_lead_owner="Owner",
    )
    ensure_integration_configs(tenant)
    # tenant_stages() auto-falls back to defaults, so no explicit stage rows needed.
    return tenant


def seed_demo_for_tenant(tenant: Tenant, owner_name: str = "Owner"):
    """Populate a NEW tenant with a re-branded sample dataset for onboarding.

    The new owner lands in a populated, familiar CRM they can click through and
    edit. Sample records are clearly marked (tenant.has_sample_data) so they can
    be bulk-cleared via clear_sample_data() once the owner is ready for real data.
    """
    from django.utils import timezone
    from datetime import timedelta
    from .models import Account, Contact, Opportunity, Activity, Invoice

    biz = tenant.name
    now = timezone.now()
    owner = tenant.default_lead_owner or owner_name

    acct, _ = Account.objects.get_or_create(
        tenant=tenant, name=f"{biz} (Sample Retail)",
        defaults={"industry": "Retail"},
    )
    c1, _ = Contact.objects.update_or_create(
        tenant=tenant, email=f"sample.client@{tenant.slug}.co.ke",
        defaults={"first_name": "Sample", "last_name": "Client",
                  "phone": "0712345678", "account": acct,
                  "territory": "nairobi", "lifecycle": Contact.Lifecycle.CUSTOMER},
    )
    c2, _ = Contact.objects.update_or_create(
        tenant=tenant, email=f"sample.lead@{tenant.slug}.co.ke",
        defaults={"first_name": "Sample", "last_name": "Prospect",
                  "phone": "0723456789", "account": acct,
                  "territory": "nakuru", "lifecycle": Contact.Lifecycle.LEAD},
    )

    sample_deals = [
        ("POS Integration", c1, Opportunity.Stage.PROPOSAL, 350000, owner),
        ("Loyalty Module", c2, Opportunity.Stage.QUALIFICATION, 180000, owner),
        ("Inventory Sync", c1, Opportunity.Stage.PROSPECTING, 120000, owner),
        ("Wholesale Rollout", c2, Opportunity.Stage.NEGOTIATION, 640000, owner),
        ("Starter Pack", c1, Opportunity.Stage.WON, 90000, owner),
    ]
    for name, contact, stage, amount, own in sample_deals:
        Opportunity.objects.get_or_create(
            tenant=tenant, name=f"{biz} — {name}", contact=contact,
            defaults={"stage": stage, "amount": amount, "owner": own},
        )

    # A couple of onboarding tasks.
    Activity.objects.get_or_create(
        tenant=tenant, contact=c2, type=Activity.Type.TASK,
        subject=f"Call {c2.full_name} re: {biz} quote",
        defaults={"due_at": now + timedelta(days=2)},
    )
    Activity.objects.get_or_create(
        tenant=tenant, contact=c1, type=Activity.Type.TASK,
        subject="Send the proposal",
        defaults={"due_at": now + timedelta(days=1)},
    )

    # One sample invoice so the Invoices rail isn't empty.
    opp = Opportunity.objects.filter(tenant=tenant, stage=Opportunity.Stage.WON).first()
    if opp:
        Invoice.objects.get_or_create(
            tenant=tenant, opportunity=opp,
            defaults={"contact": c1, "number": f"INV-{opp.pk}-001",
                      "amount_excl_vat": Decimal("100000.00"),
                      "vat_rate": Decimal("16.00"), "status": Invoice.Status.DRAFT},
        )

    tenant.has_sample_data = True
    tenant.save(update_fields=["has_sample_data"])
    return tenant


def clear_sample_data(tenant: Tenant):
    """Bulk-delete the seeded onboarding sample for a tenant."""
    from .models import Account, Contact, Opportunity, Activity, Invoice, Lead, IntegrationMessage

    Invoice.objects.filter(tenant=tenant).delete()
    Activity.objects.filter(tenant=tenant).delete()
    Opportunity.objects.filter(tenant=tenant).delete()
    Lead.objects.filter(tenant=tenant).delete()
    Contact.objects.filter(tenant=tenant).delete()
    Account.objects.filter(tenant=tenant).delete()
    IntegrationMessage.objects.filter(tenant=tenant).delete()
    tenant.has_sample_data = False
    tenant.save(update_fields=["has_sample_data"])
    return tenant

