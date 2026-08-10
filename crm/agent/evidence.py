"""The evidence ledger: what counts as proof, and what proof is allowed to do.

The rule the whole agent layer is built on: **nothing about a person is
guessed.** Tools report observations — "this string appeared in a signature
block on activity #91" — and the ledger prices the *source* of the observation
into a strength. Strength, not the model's opinion, decides the outcome:

    strength >= WRITE_THRESHOLD    write it to the record
    strength >= SUGGEST_THRESHOLD  hold it as a Suggestion for a human
    below that                     discard it, and say why in the run trail

Why the asymmetry: a blank field is honest, and anybody looking at it knows to
go and find the answer. A confidently wrong field is indistinguishable from a
correct one, so it poisons every later decision — including the agent's own.
Cheap writes are therefore expensive, and the threshold sits high.

Two further guards:

* ``WRITABLE_FIELDS`` — the agent may correct *facts* (a phone number, a
  company domain). It may not touch *judgements*: lifecycle, pipeline stage,
  BANT scores, deal ownership. Those belong to the rep, and an agent that can
  move a deal to Won is an agent that can fake a quarter.
* An existing value is only overwritten by evidence meaningfully stronger than
  whatever put it there (``OVERWRITE_MARGIN``). Filling a blank is easy;
  contradicting a human is not.
"""

from django.utils import timezone

from ..models import Account, Contact, Evidence, Lead, Opportunity, Subject, Suggestion

# ---------------------------------------------------------------------------
# The price list
#
# Read this as "how much would I bet that a value from this source is right?"
# Sources are named observation-first (`crm.signature-block`, not `title`) so a
# reviewer can always ask the more useful question: where did you see that?
# ---------------------------------------------------------------------------
SOURCE_STRENGTH = {
    # Money moved. The payer's phone and name are as verified as this CRM gets.
    "crm.payment-confirmation": 95,
    # The buyer typed their own name into the deal room to accept.
    "crm.deal-room-acceptance": 92,
    # A human put it there while talking to the person.
    "crm.human-entry": 80,
    # Parsed out of a signature block on a logged email.
    "crm.signature-block": 78,
    # The lead's own web-form submission.
    "crm.form-submission": 74,
    # Company domain derived from a work email address (not gmail/yahoo/etc.).
    "crm.email-domain": 66,
    # Someone wrote it in the body of a note. People paraphrase in notes.
    "crm.activity-text": 45,
    # A published profile page naming the person.
    "web.profile": 55,
    # A search result that mentions them.
    "web.search": 40,
    # Derived from a formatting convention (e.g. numbering scheme).
    "crm.pattern-inference": 30,
    # The model thinks so. Priced at zero on purpose: it can never write, and
    # it can never even become a suggestion. If this is all we have, we have
    # nothing, and the honest output is a question for a human.
    "model.guess": 0,
}

WRITE_THRESHOLD = 70
SUGGEST_THRESHOLD = 25
OVERWRITE_MARGIN = 15

# Facts the agent may correct, per subject type. Everything absent from this
# map is off-limits — see the module docstring.
WRITABLE_FIELDS = {
    Subject.CONTACT: {
        "first_name", "last_name", "email", "phone", "job_title", "territory",
        "date_of_birth", "personal_notes",
    },
    Subject.ACCOUNT: {"industry", "website", "phone", "billing_address", "notes"},
    Subject.OPPORTUNITY: {"expected_close_date", "amount"},
    Subject.LEAD: {"first_name", "last_name", "email", "phone", "company", "territory"},
}

SUBJECT_MODELS = {
    Subject.CONTACT: Contact,
    Subject.ACCOUNT: Account,
    Subject.OPPORTUNITY: Opportunity,
    Subject.LEAD: Lead,
}


def price(source: str) -> int:
    """Strength (0-100) for an observation source. Unknown sources are worthless."""
    return SOURCE_STRENGTH.get(source, 0)


def is_writable(subject_type: str, field: str) -> bool:
    return field in WRITABLE_FIELDS.get(subject_type, set())


def resolve_subject(tenant, subject_type: str, subject_id):
    """Fetch a subject record, always scoped to the tenant."""
    model = SUBJECT_MODELS.get(subject_type)
    if model is None:
        return None
    return model.objects.filter(tenant=tenant, pk=subject_id).first()


def current_strength(tenant, subject_type, subject_id, field, value):
    """How strong is the evidence behind the value already on the record?

    An empty field has no defender. A field whose current value matches an
    applied observation is defended by that observation's strength. A value
    with no ledger entry at all was typed by a human, so it gets human-entry
    strength — the agent should not casually overwrite a colleague.
    """
    if value in (None, ""):
        return 0
    match = (
        Evidence.objects.filter(
            tenant=tenant, subject_type=subject_type, subject_id=subject_id,
            field=field, value=str(value), applied=True,
        )
        .order_by("-strength")
        .first()
    )
    if match:
        return match.strength
    return SOURCE_STRENGTH["crm.human-entry"]


def record_observation(
    tenant, subject_type, subject_id, field, value, source,
    source_detail="", run=None, observed_at=None, rationale="",
):
    """Log an observation and let the ledger decide what it earns.

    Returns a dict describing the outcome — ``applied``, ``suggested`` or
    ``discarded`` plus the reason — which the caller writes into the run trail
    so the decision is legible afterwards.
    """
    value = "" if value is None else str(value).strip()
    strength = price(source)
    observed_at = observed_at or timezone.now()

    if not value:
        return {"outcome": "discarded", "reason": "empty value", "strength": strength}

    subject = resolve_subject(tenant, subject_type, subject_id)
    if subject is None:
        return {"outcome": "discarded", "reason": "subject not found", "strength": strength}

    if not is_writable(subject_type, field):
        return {
            "outcome": "discarded",
            "reason": (
                f"'{field}' is not a fact the agent may set on a {subject_type} — "
                "it is a human judgement"
            ),
            "strength": strength,
        }

    existing = getattr(subject, field, None)
    existing_str = "" if existing in (None, "") else str(existing)
    if existing_str == value:
        # Same value, fresh sighting: no change, but the confirmation is worth
        # storing — it is exactly what keeps the Trust Score from decaying.
        evidence = Evidence.objects.create(
            tenant=tenant, subject_type=subject_type, subject_id=subject_id,
            field=field, value=value, source=source, source_detail=source_detail,
            strength=strength, observed_at=observed_at, run=run, applied=True,
        )
        return {
            "outcome": "confirmed", "reason": "matches the value already on record",
            "strength": strength, "evidence_id": evidence.id,
        }

    # A human already said no to exactly this change. Re-proposing it every
    # time the agent runs is the fastest way to teach a team to ignore the
    # review queue, so a rejection is remembered.
    rejected = Suggestion.objects.filter(
        tenant=tenant, subject_type=subject_type, subject_id=subject_id,
        field=field, proposed_value=value, status=Suggestion.Status.REJECTED,
    ).exists()
    if rejected:
        return {
            "outcome": "discarded",
            "reason": "a human already rejected this exact change",
            "strength": strength,
        }

    evidence = Evidence.objects.create(
        tenant=tenant, subject_type=subject_type, subject_id=subject_id,
        field=field, value=value, source=source, source_detail=source_detail,
        strength=strength, observed_at=observed_at, run=run, applied=False,
    )

    defender = current_strength(tenant, subject_type, subject_id, field, existing_str)
    clears_write_bar = strength >= WRITE_THRESHOLD
    beats_incumbent = not existing_str or strength >= defender + OVERWRITE_MARGIN

    if clears_write_bar and beats_incumbent:
        setattr(subject, field, value)
        subject.save(update_fields=[field, "updated_at"])
        evidence.applied = True
        evidence.save(update_fields=["applied"])
        return {
            "outcome": "applied", "strength": strength, "evidence_id": evidence.id,
            "reason": (
                f"{source} is strong enough to write"
                if not existing_str
                else f"{source} ({strength}) outweighs what was there ({defender})"
            ),
        }

    if strength >= SUGGEST_THRESHOLD:
        reason = (
            f"{source} is below the write threshold"
            if not clears_write_bar
            else f"the existing value is backed by stronger evidence ({defender})"
        )
        # The agent re-reads the same signature block every time it runs. One
        # pending proposal per change, not one per run.
        pending = Suggestion.objects.filter(
            tenant=tenant, subject_type=subject_type, subject_id=subject_id,
            field=field, proposed_value=value, status=Suggestion.Status.PENDING,
        ).first()
        if pending:
            return {
                "outcome": "suggested", "reason": "already awaiting review",
                "strength": strength, "evidence_id": evidence.id,
                "suggestion_id": pending.id,
            }
        suggestion = Suggestion.objects.create(
            tenant=tenant, subject_type=subject_type, subject_id=subject_id,
            field=field, current_value=existing_str, proposed_value=value,
            rationale=rationale or f"Observed via {source}. {source_detail}".strip(),
            confidence=strength, evidence=evidence, run=run,
        )
        return {
            "outcome": "suggested", "reason": reason, "strength": strength,
            "evidence_id": evidence.id, "suggestion_id": suggestion.id,
        }

    return {
        "outcome": "discarded",
        "reason": f"{source} is too weak to act on ({strength})",
        "strength": strength, "evidence_id": evidence.id,
    }


def accept_suggestion(suggestion: Suggestion, decided_by=""):
    """A human said yes: write the value and promote its evidence."""
    if suggestion.status != Suggestion.Status.PENDING:
        return suggestion
    subject = resolve_subject(
        suggestion.tenant, suggestion.subject_type, suggestion.subject_id
    )
    if subject is not None and is_writable(suggestion.subject_type, suggestion.field):
        setattr(subject, suggestion.field, suggestion.proposed_value)
        subject.save(update_fields=[suggestion.field, "updated_at"])
        if suggestion.evidence:
            # A human vouching for it is the strongest signal available; record
            # that so the value is not re-flagged as unverified next week.
            suggestion.evidence.applied = True
            suggestion.evidence.strength = max(
                suggestion.evidence.strength, SOURCE_STRENGTH["crm.human-entry"]
            )
            suggestion.evidence.save(update_fields=["applied", "strength"])
    suggestion.status = Suggestion.Status.ACCEPTED
    suggestion.decided_at = timezone.now()
    suggestion.decided_by = decided_by
    suggestion.save(update_fields=["status", "decided_at", "decided_by", "updated_at"])
    return suggestion


def reject_suggestion(suggestion: Suggestion, decided_by=""):
    """A human said no. The observation stays in the ledger — a rejected
    proposal is evidence about the *source*, and worth keeping."""
    if suggestion.status != Suggestion.Status.PENDING:
        return suggestion
    suggestion.status = Suggestion.Status.REJECTED
    suggestion.decided_at = timezone.now()
    suggestion.decided_by = decided_by
    suggestion.save(update_fields=["status", "decided_at", "decided_by", "updated_at"])
    return suggestion


def pending_suggestions(tenant):
    return Suggestion.objects.filter(tenant=tenant, status=Suggestion.Status.PENDING)
