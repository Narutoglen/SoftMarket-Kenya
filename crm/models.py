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

M7+ layers the agentic core on top (see ``crm/agent/``):
  * The agent owns a work queue and runs on its own clock — records improve
    between logins instead of only when a rep types something.
  * Nothing about a person is guessed: tools record *observations* into an
    Evidence ledger, and only strong evidence writes to a record. Weak
    evidence becomes a Suggestion a human accepts or rejects.
  * Every field therefore carries provenance, which is what makes the Trust
    Score / decay radar possible (``crm/trust.py``).
"""

import secrets

from django.db import models


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

    def get_absolute_url(self):
        return f"/crm/accounts/{self.pk}/"


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
    # Role at the account. Almost always the first thing an email signature
    # gives up, and the thing that decides whether this person can sign.
    job_title = models.CharField(max_length=120, blank=True)
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

    def get_absolute_url(self):
        return f"/crm/contacts/{self.pk}/"


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
    # Manual ordering within a stage column (drag-to-reorder). Lower = higher up.
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["stage", "order", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_stage_display()})"


# ---------------------------------------------------------------------------
# M6 — White-label config: per-tenant pipeline stages + integrations
# ---------------------------------------------------------------------------
class TenantStage(InstanceScopedModel):
    """A configurable pipeline stage for ONE tenant.

    Replaces the hard-coded Opportunity.Stage enum for display/branding: each
    tenant gets its own ordered stage list with its own win-probability. The
    Opportunity.stage value is the stage `key` (stable slug), so existing deals
    keep working even if a tenant renames a stage.
    """

    key = models.SlugField(max_length=30, help_text="Stable slug, e.g. 'proposal'")
    label = models.CharField(max_length=60, help_text="Display name, e.g. 'Proposal'")
    order = models.PositiveIntegerField(default=0)
    probability = models.PositiveSmallIntegerField(
        default=50, help_text="Default win-probability (%) for the weighted forecast."
    )
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)

    class Meta:
        ordering = ["tenant", "order"]
        unique_together = [("tenant", "key")]

    def __str__(self):
        return f"{self.label} ({self.tenant.slug})"


class IntegrationConfig(InstanceScopedModel):
    """Per-tenant toggles + placeholder creds for the Kenyan-market channels.

    Milestone 6 wires the *contracts* only — no live third-party calls. Real
    credentials are filled per tenant later (kept out of code / in env).
    """

    class Channel(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        WHATSAPP = "whatsapp", "WhatsApp"
        ETIMS = "etims", "eTIMS"
        OFFLINE = "offline", "Offline sync"

    channel = models.CharField(max_length=20, choices=Channel.choices)
    enabled = models.BooleanField(default=False)
    # Placeholder config (no secrets here). Per-channel fields added as needed.
    config_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["channel"]
        unique_together = [("tenant", "channel")]

    def __str__(self):
        return f"{self.get_channel_display()} ({'on' if self.enabled else 'off'})"


class IntegrationMessage(InstanceScopedModel):
    """Outbound message queue for integration channels (M-Pesa/WhatsApp/etc.).

    The integration service enqueues here; a worker (later) drains it. Milestone
    6 proves the queue + enqueue path, not the live delivery.
    """

    class Channel(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        WHATSAPP = "whatsapp", "WhatsApp"
        ETIMS = "etims", "eTIMS"
        OFFLINE = "offline", "Offline sync"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    channel = models.CharField(max_length=20, choices=Channel.choices)
    recipient = models.CharField(max_length=200, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_channel_display()} -> {self.recipient} ({self.status})"


# ---------------------------------------------------------------------------
# M7 — the agentic layer
#
# The agent is not a chat box bolted onto the CRM: it has its own work queue,
# its own clock, and its own audit trail. Reps see what it did, why it did it,
# and what it wants permission to change.
# ---------------------------------------------------------------------------
class Subject(models.TextChoices):
    """Which CRM record a piece of agent work is about.

    Deliberately a (type, id) pair rather than Django's contenttypes: the
    subject is always one of four tenant-scoped models, and a plain slug keeps
    the JSON API, the tool arguments, and the tenant filter all readable.
    """

    CONTACT = "contact", "Contact"
    ACCOUNT = "account", "Account"
    OPPORTUNITY = "opportunity", "Opportunity"
    LEAD = "lead", "Lead"


class SubjectScopedModel(InstanceScopedModel):
    """Abstract base for rows that point at one CRM record."""

    subject_type = models.CharField(max_length=20, choices=Subject.choices)
    subject_id = models.PositiveIntegerField()

    class Meta:
        abstract = True

    @property
    def subject(self):
        """Resolve the referenced record, scoped to this row's tenant."""
        model = {
            Subject.CONTACT: Contact,
            Subject.ACCOUNT: Account,
            Subject.OPPORTUNITY: Opportunity,
            Subject.LEAD: Lead,
        }.get(self.subject_type)
        if model is None:
            return None
        return model.objects.filter(tenant_id=self.tenant_id, pk=self.subject_id).first()

    @property
    def subject_label(self):
        obj = self.subject
        return str(obj) if obj else f"{self.get_subject_type_display()} #{self.subject_id}"


class AgentTask(SubjectScopedModel):
    """One unit of work on the agent's queue.

    Scheduling is by ``due_at`` rather than cron: the agent decides when a
    record is worth another look and says why (``reason``), which is the line
    the rep reads on the record's Agent tab.

    Claiming uses a *lease*: a dispatcher stamps ``lease_owner`` /
    ``lease_expires_at`` inside a row lock, so several dispatchers can run
    against one database and still take disjoint work. If a worker dies its
    lease simply expires and the task becomes claimable again — no cleanup job.
    """

    class Kind(models.TextChoices):
        RESEARCH_CONTACT = "research_contact", "Research contact"
        ENRICH_ACCOUNT = "enrich_account", "Enrich account"
        VERIFY_FIELD = "verify_field", "Re-verify stale field"
        REVIEW_DEAL = "review_deal", "Review deal health"
        RECONCILE_PAYMENT = "reconcile_payment", "Reconcile payment"
        DEAL_ROOM_SIGNAL = "deal_room_signal", "Follow up on deal-room activity"
        BRIEF = "brief", "Write a briefing"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    reason = models.TextField(
        blank=True, help_text="Why this was scheduled — shown to the rep, in plain words."
    )
    payload = models.JSONField(default=dict, blank=True)
    due_at = models.DateTimeField(db_index=True)
    priority = models.IntegerField(default=0, help_text="Lower runs first.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    lease_owner = models.CharField(max_length=80, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    last_error = models.TextField(blank=True)
    # Set when the agent itself asked for the recheck, so the UI can separate
    # "the agent wants another look" from "a human queued this".
    scheduled_by_agent = models.BooleanField(default=False)

    class Meta:
        ordering = ["priority", "due_at", "id"]
        indexes = [
            models.Index(fields=["tenant", "status", "due_at"]),
            models.Index(fields=["subject_type", "subject_id"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} → {self.subject_label} ({self.status})"


class AgentRun(InstanceScopedModel):
    """One execution of the agent loop, with the brief it produced."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    task = models.ForeignKey(
        AgentTask, on_delete=models.SET_NULL, null=True, blank=True, related_name="runs"
    )
    planner = models.CharField(
        max_length=20, default="playbook",
        help_text="'claude' when an LLM planned the run, 'playbook' for the deterministic path.",
    )
    model = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    brief = models.TextField(blank=True, help_text="What the agent concluded, for a human.")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Run #{self.pk} ({self.planner}/{self.status})"


class AgentStep(InstanceScopedModel):
    """A single tool call inside a run — the Agent tab is a list of these.

    Steps are kept even when the agent decides *not* to act ("discarded this
    lead because the domain belongs to a mail provider"), because the discard
    reasoning is the most useful part of the trail for a sceptical rep.
    """

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    seq = models.PositiveSmallIntegerField(default=0)
    tool = models.CharField(max_length=60)
    tool_input = models.JSONField(default=dict, blank=True)
    tool_output = models.JSONField(default=dict, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    ok = models.BooleanField(default=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["run", "seq"]

    def __str__(self):
        return f"{self.seq}. {self.tool}"


class Evidence(SubjectScopedModel):
    """An *observation* about one field of one record.

    Tools never report a conclusion with a confidence number attached; they
    report what they saw and where they saw it (``source``, e.g.
    ``crm.signature-block``). The ledger in ``crm/agent/evidence.py`` prices
    that source into a strength, and the strength decides whether the value is
    written straight to the record or held back as a Suggestion.

    This table is also the provenance layer the Trust Score reads: a field with
    a recent, strong observation is trustworthy; the same field with nothing
    behind it but a rep's typing from 14 months ago is not.
    """

    field = models.CharField(max_length=60, help_text="e.g. 'phone', 'industry'")
    value = models.TextField(blank=True)
    source = models.SlugField(
        max_length=60, help_text="Observation kind, e.g. 'crm.signature-block'"
    )
    source_detail = models.CharField(
        max_length=300, blank=True, help_text="Where exactly — activity id, URL, payment ref."
    )
    strength = models.PositiveSmallIntegerField(
        default=0, help_text="0-100, priced from `source` by the evidence ledger."
    )
    observed_at = models.DateTimeField(help_text="When the observation was made, not when stored.")
    run = models.ForeignKey(
        AgentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence"
    )
    applied = models.BooleanField(
        default=False, help_text="True if this observation was written to the record."
    )

    class Meta:
        ordering = ["-observed_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "subject_type", "subject_id", "field"]),
        ]

    def __str__(self):
        return f"{self.field}={self.value!r} via {self.source} ({self.strength})"


class Suggestion(SubjectScopedModel):
    """A proposed field change waiting on a human.

    A confidently wrong fact about a customer is worse than a blank field —
    once written you can no longer tell it apart from a true one. So anything
    the ledger prices below the write threshold lands here instead.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    field = models.CharField(max_length=60)
    current_value = models.TextField(blank=True)
    proposed_value = models.TextField(blank=True)
    rationale = models.TextField(blank=True)
    confidence = models.PositiveSmallIntegerField(default=0)
    evidence = models.ForeignKey(
        Evidence, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggestions"
    )
    run = models.ForeignKey(
        AgentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggestions"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self):
        return f"{self.field}: {self.current_value!r} → {self.proposed_value!r}"


class AgentQuestion(SubjectScopedModel):
    """Something the agent could not settle from evidence and wants asked."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ANSWERED = "answered", "Answered"
        DISMISSED = "dismissed", "Dismissed"

    question = models.TextField()
    context = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    run = models.ForeignKey(
        AgentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.question[:80]


# ---------------------------------------------------------------------------
# Bonus 1 — payments-aware pipeline (M-Pesa reconciliation)
#
# Every global CRM assumes money arrives by card or invoice and lands in an
# accounting system somebody else owns. In this market it arrives as an M-Pesa
# confirmation on a phone. Treating that confirmation as a first-class CRM
# event is what lets a deal close itself.
# ---------------------------------------------------------------------------
class PaymentEvent(InstanceScopedModel):
    class Channel(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"

    class Status(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        MATCHED = "matched", "Matched"
        NEEDS_REVIEW = "needs_review", "Needs review"
        IGNORED = "ignored", "Ignored"

    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.MPESA)
    # M-Pesa transaction code (e.g. TGH4X8K9LM). Unique per tenant so replaying
    # the same SMS — a very common support action — can never double-count.
    external_ref = models.CharField(max_length=40, blank=True)
    payer_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_text = models.TextField(blank=True, help_text="The confirmation as received.")
    raw_payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=14, choices=Status.choices, default=Status.UNMATCHED)
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    match_confidence = models.PositiveSmallIntegerField(default=0)
    match_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-paid_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_ref"],
                condition=models.Q(external_ref__gt=""),
                name="unique_payment_ref_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.get_channel_display()} {self.amount} from {self.payer_name or self.phone}"


# ---------------------------------------------------------------------------
# Bonus 2 — the client-facing Deal Room
#
# A shareable page per deal: what was quoted, where it stands, how to pay, and
# an Accept button. Opens are tracked, so "opened the quote four times, never
# replied" becomes a pipeline signal instead of a hunch.
# ---------------------------------------------------------------------------
def new_room_token():
    return secrets.token_urlsafe(16)


class DealRoom(InstanceScopedModel):
    opportunity = models.OneToOneField(
        Opportunity, on_delete=models.CASCADE, related_name="deal_room"
    )
    token = models.CharField(max_length=48, unique=True, default=new_room_token)
    headline = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)
    # [{"label": "...", "qty": 1, "unit_price": 120000}]
    line_items = models.JSONField(default=list, blank=True)
    terms = models.TextField(blank=True)
    next_step = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by_name = models.CharField(max_length=160, blank=True)
    accepted_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Deal room: {self.opportunity.name}"

    @property
    def total(self):
        total = 0
        for item in self.line_items or []:
            try:
                total += int(item.get("qty", 1)) * int(item.get("unit_price", 0))
            except (TypeError, ValueError):
                continue
        return total or self.opportunity.amount

    def get_absolute_url(self):
        return f"/room/{self.token}/"


class DealRoomView(InstanceScopedModel):
    """One open of a deal room. Engagement, not analytics vanity."""

    room = models.ForeignKey(DealRoom, on_delete=models.CASCADE, related_name="views")
    viewed_at = models.DateTimeField(auto_now_add=True)
    # Hashed, never the raw address — the buyer did not consent to being logged.
    visitor_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    referrer = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-viewed_at"]

    def __str__(self):
        return f"View of {self.room_id} at {self.viewed_at}"
