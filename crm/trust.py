"""Trust Score and decay radar — how much of this record still deserves belief?

The industry's own numbers are the argument for this feature: most teams say
under half their CRM data is accurate, and a database left alone drifts from
roughly 97% correct at month one to the mid-70s by month twelve. People change
jobs, numbers, and companies; the CRM does not notice. Every CRM shows you a
phone number. Almost none of them tell you that nobody has confirmed it since
2024, which is the thing you actually need to know before you dial.

Because the agent layer already writes provenance for every field it touches
(``crm/agent/evidence.py``), the raw material is here. This module turns it
into three things:

* **Per-field confidence** — the strength of the best observation behind the
  current value, decayed by how long ago it was made. Different fields rot at
  different speeds: a mobile number goes stale faster than a company's
  industry, so each field carries its own half-life.
* **A record Trust Score** — a weighted roll-up, with missing fields counting
  as zero, so completeness and freshness land in one number.
* **The decay radar** — the worst-scoring records, and a hook to queue the
  agent to re-verify specific fields rather than re-research everything.

A field with no ledger entry is *unverified*, not wrong. Somebody typed it once
and it may well be fine — but it has never been confirmed, and it decays from
the day the record was created rather than from a confirmation that never
happened.
"""

from datetime import timedelta

from django.utils import timezone

from .agent.evidence import SOURCE_STRENGTH
from .models import Account, AgentTask, Contact, Evidence, Subject

# (field, label, weight, half-life in days)
#
# Half-lives are judgement calls, tuned to how fast the underlying fact moves
# in the real world — not to how often the column gets written.
FIELD_SPECS = {
    Subject.CONTACT: [
        ("first_name", "First name", 2, 1460),
        ("last_name", "Last name", 2, 1460),
        ("email", "Email", 3, 540),
        ("phone", "Phone", 3, 300),
        # Titles change with every promotion and reorg — the fastest-rotting
        # field on the record, and the one most likely to embarrass you.
        ("job_title", "Job title", 2, 400),
        ("account", "Company", 2, 540),
        ("territory", "Territory", 1, 730),
    ],
    Subject.ACCOUNT: [
        ("industry", "Industry", 2, 1095),
        ("website", "Website", 2, 900),
        ("phone", "Phone", 2, 365),
        ("billing_address", "Billing address", 1, 730),
    ],
}

# A value nobody has ever confirmed starts here — the same strength as a rep
# typing it, because that is exactly what it is.
UNVERIFIED_BASE = SOURCE_STRENGTH["crm.human-entry"]

VERIFIED_AT = 60   # at or above: believe it
AGING_AT = 35      # between: believe it, but confirm before it matters
                   # below: treat as unknown


def _decay(base: int, age_days: float, half_life_days: int) -> int:
    """Exponential decay. Half the confidence per half-life elapsed."""
    if base <= 0:
        return 0
    if age_days <= 0:
        return int(base)
    return int(round(base * (0.5 ** (age_days / float(half_life_days)))))


def _display_value(obj, field):
    value = getattr(obj, field, None)
    if field == "account":
        return obj.account.name if getattr(obj, "account_id", None) else ""
    return "" if value in (None, "") else str(value)


def field_confidence(obj, subject_type, field, half_life_days):
    """Confidence in one field of one record, with the reason behind it."""
    now = timezone.now()
    value = _display_value(obj, field)
    if not value:
        return {
            "field": field, "value": "", "state": "missing", "confidence": 0,
            "source": "", "verified_at": None, "age_days": None,
            "explanation": "No value on record.",
        }

    evidence = (
        Evidence.objects.filter(
            tenant_id=obj.tenant_id, subject_type=subject_type, subject_id=obj.pk,
            field=field, value=value, applied=True,
        )
        .order_by("-strength", "-observed_at")
        .first()
    )

    if evidence:
        age_days = (now - evidence.observed_at).total_seconds() / 86400.0
        confidence = _decay(evidence.strength, age_days, half_life_days)
        source, verified_at = evidence.source, evidence.observed_at
        explanation = f"Confirmed via {evidence.source} {int(age_days)} days ago."
    else:
        # Never confirmed. Decay from record creation — that is the last moment
        # we can honestly claim anybody looked at this value.
        age_days = (now - obj.created_at).total_seconds() / 86400.0
        confidence = _decay(UNVERIFIED_BASE, age_days, half_life_days)
        source, verified_at = "", None
        explanation = f"Entered by hand {int(age_days)} days ago, never confirmed since."

    if confidence < AGING_AT:
        state = "stale"
    elif confidence < VERIFIED_AT:
        state = "aging"
    elif not evidence:
        state = "unverified"
    else:
        state = "verified"

    return {
        "field": field, "value": value, "state": state, "confidence": confidence,
        "source": source, "verified_at": verified_at,
        "age_days": int(age_days), "explanation": explanation,
    }


def trust_report(obj, subject_type=None):
    """Per-field confidence plus the rolled-up Trust Score for a record."""
    subject_type = subject_type or (
        Subject.CONTACT if isinstance(obj, Contact) else Subject.ACCOUNT
    )
    specs = FIELD_SPECS.get(subject_type, [])
    fields, weighted, total_weight = [], 0, 0
    for field, label, weight, half_life in specs:
        row = field_confidence(obj, subject_type, field, half_life)
        row["label"] = label
        row["weight"] = weight
        row["half_life_days"] = half_life
        fields.append(row)
        weighted += row["confidence"] * weight
        total_weight += weight

    score = int(round(weighted / total_weight)) if total_weight else 0
    problems = [f for f in fields if f["state"] in ("missing", "stale")]
    return {
        "score": score,
        "band": score_band(score),
        "fields": fields,
        "problems": problems,
        "verified_count": sum(1 for f in fields if f["state"] == "verified"),
        "field_count": len(fields),
    }


def score_band(score: int) -> str:
    if score >= 70:
        return "good"
    if score >= 45:
        return "watch"
    return "poor"


def decay_radar(tenant, limit=25, threshold=55):
    """Records whose data has rotted the furthest, worst first.

    Scoped to contacts and accounts — the records people act on. Deals inherit
    their trust from the contact behind them, so scoring them separately would
    double-count the same rot.
    """
    rows = []
    for obj in Contact.objects.filter(tenant=tenant).select_related("account"):
        report = trust_report(obj, Subject.CONTACT)
        if report["score"] <= threshold:
            rows.append({
                "subject_type": Subject.CONTACT, "object": obj,
                "label": obj.full_name, "url": obj.get_absolute_url(), **report,
            })
    for obj in Account.objects.filter(tenant=tenant):
        report = trust_report(obj, Subject.ACCOUNT)
        if report["score"] <= threshold:
            rows.append({
                "subject_type": Subject.ACCOUNT, "object": obj,
                "label": obj.name, "url": obj.get_absolute_url(), **report,
            })
    rows.sort(key=lambda r: r["score"])
    return rows[:limit]


def portfolio_trust(tenant):
    """One number for the whole database, plus the shape of the problem."""
    scores, missing, stale = [], 0, 0
    for obj in Contact.objects.filter(tenant=tenant).select_related("account"):
        report = trust_report(obj, Subject.CONTACT)
        scores.append(report["score"])
        missing += sum(1 for f in report["fields"] if f["state"] == "missing")
        stale += sum(1 for f in report["fields"] if f["state"] == "stale")
    return {
        "average_score": int(round(sum(scores) / len(scores))) if scores else 0,
        "records": len(scores),
        "missing_fields": missing,
        "stale_fields": stale,
        "band": score_band(int(round(sum(scores) / len(scores))) if scores else 0),
    }


def queue_reverification(tenant, limit=10, threshold=45):
    """Hand the worst fields to the agent instead of nagging a human.

    One task per record, carrying the specific fields to chase, so the run has
    a narrow brief rather than "go and look at this person again".
    """
    from .agent import queue

    queued = []
    for row in decay_radar(tenant, limit=limit, threshold=threshold):
        fields = [f["field"] for f in row["problems"]]
        if not fields:
            continue
        task = queue.schedule(
            tenant=tenant,
            kind=AgentTask.Kind.VERIFY_FIELD,
            subject_type=row["subject_type"],
            subject_id=row["object"].pk,
            reason=(
                f"Trust score {row['score']}/100 — "
                f"{', '.join(f['label'] for f in row['problems'][:3])} "
                f"{'is' if len(row['problems']) == 1 else 'are'} missing or stale."
            ),
            payload={"fields": fields},
            priority=-1,
            by_agent=True,
        )
        queued.append(task)
    return queued


def confirm_field(tenant, subject_type, subject_id, field, value, source, detail=""):
    """Shorthand used by other modules to record 'we just saw this again'.

    Re-confirming a value that has not changed is the cheapest way to keep a
    record trustworthy, and it is what a payment or a deal-room acceptance
    quietly gives us for free.
    """
    return Evidence.objects.create(
        tenant=tenant, subject_type=subject_type, subject_id=subject_id,
        field=field, value=str(value), source=source, source_detail=detail,
        strength=SOURCE_STRENGTH.get(source, 0), observed_at=timezone.now(), applied=True,
    )


def recently_verified(tenant, days=7, limit=20):
    """What the agent has confirmed lately — the counterweight to the radar."""
    since = timezone.now() - timedelta(days=days)
    return (
        Evidence.objects.filter(tenant=tenant, applied=True, observed_at__gte=since)
        .order_by("-observed_at")[:limit]
    )
