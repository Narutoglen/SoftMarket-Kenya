"""White-label CRM core for SoftMarket Collective.

Design goal (per team agreement): one reusable CRM *core* that ships configured
per client. SoftMarket is the first instance (tenant slug ``softmarket``). A
second client later = a new ``Tenant`` row + styling/config, NOT a code fork.

Every CRM record is scoped to a ``Tenant`` via ``InstanceScopedModel`` so the
same tables serve every client in isolation. This mirrors the contact-centric
data model from the CRM domain skills (Contact is the hub; Account / Activity /
Lead / Opportunity all relate to it).

Borrowed from FrugalTech CRM teaching:
  * Retention economics -> nurture relationships, catch churn early.
  * 360-degree view -> one Contact shows every call/email/note/deal.
  * BANT (Budget, Authority, Need, Timeline) -> hot/warm/cold lead scoring.
  * Automation: web-form -> lead -> auto-respond + auto-assign + schedule.
  * Dedupe/merge -> collapse duplicate contacts by newest-per-field.
"""

from django.db import models
from django.utils import timezone

from marketplace.models import TimeStampedModel


# ---------------------------------------------------------------------------
# Tenant (white-label instance)
# ---------------------------------------------------------------------------
class Tenant(TimeStampedModel):
    """A single configured CRM instance. SoftMarket is the seed tenant."""

    slug = models.SlugField(max_length=60, unique=True, help_text="e.g. 'softmarket'")
    name = models.CharField(max_length=120, help_text="Display name, e.g. 'SoftMarket Kenya'")
    # White-label hooks: per-instance branding/styling live here so the same
    # frontend/reports re-skin without code changes.
    brand_primary_color = models.CharField(max_length=7, default="#6d28d9")
    brand_accent_color = models.CharField(max_length=7, default="#22d3ee")
    logo_url = models.URLField(blank=True)
    # Optional public intake form slug (used by automation routing).
    default_lead_owner = models.CharField(
        max_length=120, blank=True, help_text="Fallback owner name if no territory match."
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InstanceScopedModel(TimeStampedModel):
    """Abstract base: every CRM record belongs to one Tenant (white-label)."""

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="%(class)ss"
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Account (the company a B2B contact works for)
# ---------------------------------------------------------------------------
class Account(InstanceScopedModel):
    name = models.CharField(max_length=160)
    industry = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    billing_address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant", "name")]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Contact (the hub of the 360-degree view)
# ---------------------------------------------------------------------------
class Contact(InstanceScopedModel):
    class Lifecycle(models.TextChoices):
        SUBSCRIBER = "subscriber", "Subscriber"
        LEAD = "lead", "Lead"
        CUSTOMER = "customer", "Customer"
        CHURNED = "churned", "Churned"

    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    # Personal context that fuels relationship nurturing (DOB, spouse, kids...).
    date_of_birth = models.DateField(null=True, blank=True)
    personal_notes = models.TextField(blank=True)
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="contacts"
    )
    lifecycle = models.CharField(
        max_length=20, choices=Lifecycle.choices, default=Lifecycle.SUBSCRIBER
    )
    # Territory/zipping used by automation routing (e.g. Kenyan county or postal code).
    territory = models.CharField(max_length=80, blank=True, help_text="County / region / ZIP for lead routing")

    class Meta:
        ordering = ["last_name", "first_name"]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email or f"#{self.pk}"

    def __str__(self):
        return self.full_name


# ---------------------------------------------------------------------------
# Activity (calls / emails / notes / meetings against a contact)
# ---------------------------------------------------------------------------
class Activity(InstanceScopedModel):
    class Type(models.TextChoices):
        CALL = "call", "Call"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        NOTE = "note", "Note"
        TASK = "task", "Task"

    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="activities"
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.NOTE)
    subject = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True, help_text="For tasks/follow-ups")
    done = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()}: {self.subject or self.contact}"


# ---------------------------------------------------------------------------
# Lead (suspect -> scored -> converted to Contact)
# ---------------------------------------------------------------------------
class Lead(InstanceScopedModel):
    class Rating(models.TextChoices):
        HOT = "hot", "Hot"
        WARM = "warm", "Warm"
        COLD = "cold", "Cold"
        UNRATED = "unrated", "Unrated"

    class Source(models.TextChoices):
        WEB_FORM = "web_form", "Website form"
        REFERRAL = "referral", "Referral"
        COLD_OUTREACH = "cold_outreach", "Cold outreach"
        EVENT = "event", "Event"
        OTHER = "other", "Other"

    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    company = models.CharField(max_length=160, blank=True)
    territory = models.CharField(max_length=80, blank=True)
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.WEB_FORM
    )
    message = models.TextField(blank=True)
    # BANT answers (1-3 each; 3 = strongest). Scored into `rating`.
    bant_budget = models.PositiveSmallIntegerField(default=0, help_text="1-3")
    bant_authority = models.PositiveSmallIntegerField(default=0, help_text="1-3")
    bant_need = models.PositiveSmallIntegerField(default=0, help_text="1-3")
    bant_timeline = models.PositiveSmallIntegerField(default=0, help_text="1-3")
    rating = models.CharField(
        max_length=20, choices=Rating.choices, default=Rating.UNRATED
    )
    owner = models.CharField(max_length=120, blank=True, help_text="Assigned rep (auto or manual)")
    converted_contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="source_leads"
    )
    # Set true once the auto-responder email has been queued/sent.
    auto_responded = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email or f"#{self.pk}"

    def bant_score(self):
        return self.bant_budget + self.bant_authority + self.bant_need + self.bant_timeline

    def __str__(self):
        return f"Lead: {self.full_name} ({self.get_rating_display()})"


# ---------------------------------------------------------------------------
# Opportunity (deal in the pipeline)
# ---------------------------------------------------------------------------
class Opportunity(InstanceScopedModel):
    class Stage(models.TextChoices):
        PROSPECTING = "prospecting", "Prospecting"
        QUALIFICATION = "qualification", "Qualification"
        PROPOSAL = "proposal", "Proposal"
        NEGOTIATION = "negotiation", "Negotiation"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    name = models.CharField(max_length=200)
    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="opportunities"
    )
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="opportunities"
    )
    stage = models.CharField(
        max_length=20, choices=Stage.choices, default=Stage.PROSPECTING
    )
    amount = models.PositiveIntegerField(default=0, help_text="Deal value in KSh")
    # Probability 0-100; default per stage handled in service layer if blank.
    probability = models.PositiveSmallIntegerField(null=True, blank=True)
    expected_close_date = models.DateField(null=True, blank=True)
    owner = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_stage_display()})"
