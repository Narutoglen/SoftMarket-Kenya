"""CRM service layer: BANT scoring, lead routing, dedupe/merge, reporting.

Kept separate from models (marketplace-style) so views stay thin and the logic
is reusable by the white-label core for ANY tenant instance.
"""

from django.utils import timezone

from .models import (
    Account,
    Activity,
    Contact,
    Lead,
    Opportunity,
    Tenant,
)


# ---------------------------------------------------------------------------
# BANT scoring -> hot / warm / cold
# ---------------------------------------------------------------------------
def score_lead_rating(lead: Lead) -> Lead.Rating:
    """Map a 0-12 BANT score to a rating. Hot >=9, Warm 5-8, Cold <5."""
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
