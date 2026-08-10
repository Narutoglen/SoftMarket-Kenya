"""The agent's tools.

Design rules, in priority order:

1. **Tools report observations, never conclusions.** ``extract_signature_block``
   returns "the string '+254 711 000 111' appeared under a sign-off on activity
   #91", not "the contact's phone is +254711000111". Whether that becomes a
   fact is the evidence ledger's decision, and it is made from the *source*,
   not from the model's confidence in its own reading.
2. **Every tool is tenant-scoped by construction.** The tenant comes from the
   run context, never from an argument, so no amount of creative planning can
   reach another client's data.
3. **Reads are free, writes are few.** Of the eighteen tools here, exactly
   three change a CRM record — ``record_fact`` (through the ledger),
   ``draft_followup`` and ``schedule_recheck`` — and none of them can touch a
   judgement field.

The same registry serves both planners: Claude gets the JSON schemas, the
deterministic playbook calls the functions directly. One executor, so the
audit trail and the guard rails are identical whichever one ran.
"""

import re
import time
from dataclasses import dataclass, field as dc_field
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .. import trust
from ..models import (
    Account, Activity, AgentQuestion, AgentStep, AgentTask, Contact, DealRoom,
    Evidence, Lead, Opportunity, PaymentEvent, Subject,
)
from . import evidence as ledger

TOOLS = {}


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: callable
    writes: bool = False


@dataclass
class ToolContext:
    """Everything a tool is allowed to know about the run it belongs to."""

    tenant: object
    run: object = None
    task: object = None
    seq: int = 0
    notes: list = dc_field(default_factory=list)


def tool(name, description, properties=None, required=None, writes=False):
    def decorator(fn):
        TOOLS[name] = Tool(
            name=name,
            description=description,
            schema={
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
            fn=fn,
            writes=writes,
        )
        return fn

    return decorator


def schemas():
    """Tool definitions in Messages API shape."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema}
        for t in TOOLS.values()
    ]


def call(ctx: ToolContext, name: str, **kwargs) -> dict:
    """Execute a tool and write the step to the run trail.

    The trail records failures as steps too. An agent that quietly swallows a
    tool error and carries on is an agent whose brief you cannot trust.
    """
    entry = TOOLS.get(name)
    started = time.monotonic()
    if entry is None:
        result = {"error": f"unknown tool '{name}'"}
        _log_step(ctx, name, kwargs, result, ok=False, summary="unknown tool", started=started)
        return result
    try:
        result = entry.fn(ctx, **kwargs)
        ok = "error" not in result
    except TypeError as exc:  # bad arguments from the planner
        result, ok = {"error": f"bad arguments: {exc}"}, False
    except Exception as exc:  # noqa: BLE001 — one bad tool must not kill the run
        result, ok = {"error": f"{type(exc).__name__}: {exc}"}, False
    _log_step(ctx, name, kwargs, result, ok=ok,
              summary=str(result.get("summary", ""))[:300], started=started)
    return result


def _log_step(ctx, name, kwargs, result, ok, summary, started):
    if ctx.run is None:
        return
    ctx.seq += 1
    AgentStep.objects.create(
        tenant=ctx.tenant, run=ctx.run, seq=ctx.seq, tool=name,
        tool_input=_jsonable(kwargs), tool_output=_jsonable(result),
        ok=ok, summary=summary or ("failed" if not ok else ""),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _jsonable(value):
    """Keep the trail storable — steps are JSON columns, not pickles."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# ---------------------------------------------------------------------------
# 1-3: orientation — what do we already know?
# ---------------------------------------------------------------------------
@tool(
    "read_crm_history",
    "Read the 360 timeline for a record: activities, deals and payments already on file. "
    "Always call this before researching anything — most questions are already answered here.",
    {
        "subject_type": {"type": "string", "enum": [s.value for s in Subject]},
        "subject_id": {"type": "integer"},
        "limit": {"type": "integer", "description": "How many activities to read (default 20)."},
    },
    ["subject_type", "subject_id"],
)
def read_crm_history(ctx, subject_type, subject_id, limit=20):
    subject = ledger.resolve_subject(ctx.tenant, subject_type, subject_id)
    if subject is None:
        return {"error": "subject not found in this instance"}

    contact = subject if isinstance(subject, Contact) else getattr(subject, "contact", None)
    activities = []
    if contact is not None:
        for act in contact.activities.all()[:limit]:
            activities.append({
                "id": act.id, "type": act.type, "subject": act.subject,
                "notes": act.notes[:600], "done": act.done,
                "created_at": act.created_at.isoformat(),
            })

    record = {"label": str(subject)}
    for f in ("first_name", "last_name", "email", "phone", "job_title", "territory",
              "lifecycle", "industry", "website", "stage", "amount"):
        if hasattr(subject, f):
            record[f] = str(getattr(subject, f) or "")

    return {
        "record": record,
        "activities": activities,
        "activity_count": contact.activities.count() if contact else 0,
        "last_touch": activities[0]["created_at"] if activities else None,
        "summary": f"{len(activities)} activities on file for {subject}",
    }


@tool(
    "search_crm",
    "Search this instance's contacts, accounts and deals by free text. "
    "Use it to check whether something already exists before creating or concluding anything.",
    {
        "query": {"type": "string"},
        "kind": {"type": "string", "enum": ["contact", "account", "opportunity", "any"]},
    },
    ["query"],
)
def search_crm(ctx, query, kind="any"):
    q = (query or "").strip()
    if not q:
        return {"error": "empty query"}
    results = {"contacts": [], "accounts": [], "opportunities": []}
    if kind in ("contact", "any"):
        for c in Contact.objects.filter(tenant=ctx.tenant).filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
        )[:10]:
            results["contacts"].append({"id": c.id, "name": c.full_name, "email": c.email})
    if kind in ("account", "any"):
        for a in Account.objects.filter(tenant=ctx.tenant).filter(
            Q(name__icontains=q) | Q(website__icontains=q) | Q(industry__icontains=q)
        )[:10]:
            results["accounts"].append({"id": a.id, "name": a.name, "website": a.website})
    if kind in ("opportunity", "any"):
        for o in Opportunity.objects.filter(tenant=ctx.tenant, name__icontains=q)[:10]:
            results["opportunities"].append({"id": o.id, "name": o.name, "stage": o.stage})
    total = sum(len(v) for v in results.values())
    return {**results, "summary": f"{total} match(es) for '{q}'"}


@tool(
    "identify_contact",
    "Decide whether an email address, phone number or name belongs to a contact already in the "
    "CRM. Returns the evidence for the match, or nothing. Never invents a person.",
    {
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "name": {"type": "string"},
    },
)
def identify_contact(ctx, email="", phone="", name=""):
    from ..payments import normalise_phone

    matches = []
    if email:
        for c in Contact.objects.filter(tenant=ctx.tenant, email__iexact=email.strip()):
            matches.append({"id": c.id, "name": c.full_name, "basis": "email matches exactly",
                            "strength": "strong"})
    if phone:
        target = normalise_phone(phone)
        if target:
            for c in Contact.objects.filter(tenant=ctx.tenant).exclude(phone=""):
                if normalise_phone(c.phone) == target and not any(
                    m["id"] == c.id for m in matches
                ):
                    matches.append({"id": c.id, "name": c.full_name,
                                    "basis": "phone matches exactly", "strength": "strong"})
    if name and not matches:
        for c in Contact.objects.filter(tenant=ctx.tenant):
            if c.full_name.strip().lower() == name.strip().lower():
                matches.append({"id": c.id, "name": c.full_name,
                                "basis": "full name matches", "strength": "weak — names repeat"})
    return {
        "matches": matches,
        "summary": (
            f"{len(matches)} identity match(es)" if matches
            else "no identity match — do not assume this is an existing contact"
        ),
    }


# ---------------------------------------------------------------------------
# 4-5: observation — read what is already in the record, carefully
# ---------------------------------------------------------------------------
SIGNOFF_RE = re.compile(
    r"(?:^|\n)\s*(?:--+|regards|kind regards|best regards|best|thanks|thank you|cheers|sincerely)"
    r"[,\s]*\n",
    re.IGNORECASE,
)
PHONE_IN_TEXT_RE = re.compile(r"(?:\+?254|0)[\d\s\-]{8,12}\d")
TITLE_WORDS = (
    "ceo", "cto", "coo", "cfo", "founder", "co-founder", "director", "manager",
    "head of", "lead", "officer", "supervisor", "procurement", "purchasing",
    "operations", "accountant", "engineer", "administrator", "principal", "owner",
)


@tool(
    "extract_signature_block",
    "Scan a contact's logged emails for a signature block and report the strings found in it "
    "(title, phone, company). Reports what appeared and where — it does not decide what is true.",
    {"contact_id": {"type": "integer"}},
    ["contact_id"],
)
def extract_signature_block(ctx, contact_id):
    contact = Contact.objects.filter(tenant=ctx.tenant, pk=contact_id).first()
    if contact is None:
        return {"error": "contact not found"}

    observations = []
    activities = contact.activities.filter(
        type__in=[Activity.Type.EMAIL, Activity.Type.NOTE]
    ).order_by("-created_at")[:25]

    for act in activities:
        text = act.notes or ""
        split = SIGNOFF_RE.split(text)
        if len(split) < 2:
            continue
        block = split[-1][:600]
        phone = PHONE_IN_TEXT_RE.search(block)
        if phone:
            observations.append({
                "field": "phone",
                "value": re.sub(r"[\s\-]", "", phone.group(0)),
                "source": "crm.signature-block",
                "where": f"activity #{act.id} ({act.subject or act.type})",
                "observed_at": act.created_at.isoformat(),
            })
        for line in (ln.strip(" \t·|,") for ln in block.splitlines()):
            if not line or len(line) > 80:
                continue
            lowered = line.lower()
            if any(word in lowered for word in TITLE_WORDS):
                observations.append({
                    "field": "job_title",
                    "value": line,
                    "source": "crm.signature-block",
                    "where": f"activity #{act.id} ({act.subject or act.type})",
                    "observed_at": act.created_at.isoformat(),
                })
                break

    return {
        "observations": observations,
        "scanned": len(activities),
        "summary": (
            f"{len(observations)} signature observation(s) across {len(activities)} messages"
            if observations else "no signature block found in the logged messages"
        ),
    }


FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "icloud.com", "protonmail.com", "aol.com", "ymail.com",
}


@tool(
    "enrich_company",
    "Derive what can be *observed* about an account from the CRM itself — chiefly the company "
    "domain shared by its contacts' work email addresses. Free-mail domains are discarded.",
    {"account_id": {"type": "integer"}},
    ["account_id"],
)
def enrich_company(ctx, account_id):
    account = Account.objects.filter(tenant=ctx.tenant, pk=account_id).first()
    if account is None:
        return {"error": "account not found"}

    domains, discarded = {}, []
    for contact in account.contacts.exclude(email=""):
        domain = contact.email.split("@")[-1].strip().lower()
        if not domain:
            continue
        if domain in FREE_MAIL_DOMAINS:
            discarded.append({
                "domain": domain,
                "why": "personal mail provider — says nothing about the company",
            })
            continue
        domains.setdefault(domain, []).append(contact.full_name)

    observations = []
    for domain, people in sorted(domains.items(), key=lambda kv: -len(kv[1])):
        observations.append({
            "field": "website",
            "value": f"https://{domain}",
            "source": "crm.email-domain",
            "where": f"work email of {', '.join(people[:3])}",
            "confirmations": len(people),
        })
    return {
        "observations": observations,
        "discarded": discarded,
        "summary": (
            f"{len(observations)} company domain(s) observed, {len(discarded)} discarded"
            if observations or discarded else "no work email addresses to work from"
        ),
    }


@tool(
    "web_research",
    "Look the subject up on the public web. Only works when a research provider is configured "
    "for this deployment; otherwise it reports that no source is available, which is the honest "
    "answer — do not fill the gap from memory.",
    {"query": {"type": "string"}, "purpose": {"type": "string"}},
    ["query"],
)
def web_research(ctx, query, purpose=""):
    provider = getattr(settings, "CRM_RESEARCH_PROVIDER", "")
    if not provider:
        return {
            "available": False,
            "results": [],
            "summary": (
                "No web research provider is configured for this instance. Record nothing from "
                "memory — ask a human instead (ask_human) or work from CRM evidence only."
            ),
        }
    # A provider integration plugs in here and must return cited results; until
    # one is wired the tool refuses rather than degrading into recall.
    return {
        "available": False, "results": [],
        "summary": f"Provider '{provider}' is named but no client is wired up yet.",
    }


# ---------------------------------------------------------------------------
# 6-7: the two tools that change things
# ---------------------------------------------------------------------------
@tool(
    "record_fact",
    "Submit one observation to the evidence ledger. The ledger prices the source and decides: "
    "strong sources write to the record, weaker ones become a suggestion for a human, and "
    "anything unsourced is discarded. Pass the source you actually observed it from — "
    "'model.guess' is priced at zero and will always be thrown away.",
    {
        "subject_type": {"type": "string", "enum": [s.value for s in Subject]},
        "subject_id": {"type": "integer"},
        "field": {"type": "string", "description": "e.g. phone, job_title, website, industry"},
        "value": {"type": "string"},
        "source": {"type": "string", "enum": sorted(ledger.SOURCE_STRENGTH)},
        "source_detail": {"type": "string", "description": "Exactly where you saw it."},
        "rationale": {"type": "string"},
    },
    ["subject_type", "subject_id", "field", "value", "source"],
    writes=True,
)
def record_fact(ctx, subject_type, subject_id, field, value, source,
                source_detail="", rationale=""):
    outcome = ledger.record_observation(
        ctx.tenant, subject_type, subject_id, field, value, source,
        source_detail=source_detail, run=ctx.run, rationale=rationale,
    )
    return {**outcome, "summary": f"{field}: {outcome['outcome']} — {outcome['reason']}"}


@tool(
    "schedule_recheck",
    "Put this record back on your own queue for a future date, with the reason in plain words. "
    "The reason is shown to the sales rep, so write it for them, not for a log file.",
    {
        "subject_type": {"type": "string", "enum": [s.value for s in Subject]},
        "subject_id": {"type": "integer"},
        "kind": {"type": "string", "enum": [k.value for k in AgentTask.Kind]},
        "days": {"type": "integer", "description": "Days from now."},
        "reason": {"type": "string"},
    },
    ["subject_type", "subject_id", "reason"],
    writes=True,
)
def schedule_recheck(ctx, subject_type, subject_id, reason,
                     kind=AgentTask.Kind.RESEARCH_CONTACT, days=7):
    from . import queue

    days = max(0, min(int(days or 7), 365))
    task = queue.schedule(
        tenant=ctx.tenant, kind=kind, subject_type=subject_type, subject_id=subject_id,
        reason=reason, due_in_days=days, by_agent=True,
    )
    return {
        "task_id": task.id, "due_at": task.due_at.isoformat(),
        "summary": f"rechecking in {days} day(s): {reason}",
    }


# ---------------------------------------------------------------------------
# 8-13: judgement support — read-only analysis the brief is built from
# ---------------------------------------------------------------------------
@tool(
    "flag_duplicate",
    "Look for other contacts in this instance that appear to be the same person. "
    "Reports candidates and the basis for each; merging stays a human decision.",
    {"contact_id": {"type": "integer"}},
    ["contact_id"],
)
def flag_duplicate(ctx, contact_id):
    from ..payments import normalise_phone

    contact = Contact.objects.filter(tenant=ctx.tenant, pk=contact_id).first()
    if contact is None:
        return {"error": "contact not found"}
    candidates = []
    for other in Contact.objects.filter(tenant=ctx.tenant).exclude(pk=contact.pk):
        basis = []
        if contact.email and other.email.lower() == contact.email.lower():
            basis.append("same email address")
        if contact.phone and normalise_phone(other.phone) == normalise_phone(contact.phone):
            basis.append("same phone number")
        if (
            contact.first_name and contact.last_name
            and other.full_name.lower() == contact.full_name.lower()
        ):
            basis.append("same full name")
        if basis:
            candidates.append({"id": other.id, "name": other.full_name, "basis": basis})
    return {
        "candidates": candidates,
        "summary": (
            f"{len(candidates)} possible duplicate(s)" if candidates else "no duplicates found"
        ),
    }


@tool(
    "assess_deal",
    "Read a deal's health: how long it has sat in its stage, when the contact was last touched, "
    "whether the buyer is engaging with the deal room, and what has been paid.",
    {"opportunity_id": {"type": "integer"}},
    ["opportunity_id"],
)
def assess_deal(ctx, opportunity_id):
    from .. import dealroom, payments as pay
    from .. import services

    opp = Opportunity.objects.filter(tenant=ctx.tenant, pk=opportunity_id).first()
    if opp is None:
        return {"error": "deal not found"}

    now = timezone.now()
    last_activity = opp.contact.activities.order_by("-created_at").first()
    days_quiet = (now - last_activity.created_at).days if last_activity else None
    days_in_stage = (now - opp.updated_at).days
    stage = next(
        (s for s in services.tenant_stages(ctx.tenant) if s.key == opp.stage), None
    )

    risks = []
    if days_quiet is None:
        risks.append("nobody has ever logged an interaction with this contact")
    elif days_quiet > 14:
        risks.append(f"no contact logged for {days_quiet} days")
    if days_in_stage > 21:
        risks.append(f"stuck in the same stage for {days_in_stage} days")
    if opp.expected_close_date and opp.expected_close_date < now.date():
        risks.append(f"expected close date passed on {opp.expected_close_date}")
    if not opp.expected_close_date:
        risks.append("no expected close date, so it cannot be forecast honestly")

    room = getattr(opp, "deal_room", None)
    room_state = None
    if room:
        state, label = dealroom.engagement_label(room)
        room_state = {"state": state, "label": label, **dealroom.engagement(room)}
        if state == "hot":
            risks.append("buyer is re-reading the quote but nothing has been sent back")
        if state == "cold":
            risks.append("the deal room was never opened — the link may not have landed")

    return {
        "deal": {
            "id": opp.id, "name": opp.name, "stage": opp.stage,
            "stage_label": stage.label if stage else opp.stage,
            "amount": opp.amount, "owner": opp.owner,
            "expected_close_date": (
                opp.expected_close_date.isoformat() if opp.expected_close_date else None
            ),
        },
        "days_in_stage": days_in_stage,
        "days_since_last_touch": days_quiet,
        "paid_to_date": float(pay.paid_total(opp)),
        "deal_room": room_state,
        "risks": risks,
        "summary": (
            f"{len(risks)} risk(s) on {opp.name}" if risks else f"{opp.name} looks healthy"
        ),
    }


@tool(
    "check_payments",
    "List payments recorded against a contact or deal, including any that are still waiting "
    "for a human to confirm which deal they belong to.",
    {"contact_id": {"type": "integer"}, "opportunity_id": {"type": "integer"}},
)
def check_payments(ctx, contact_id=None, opportunity_id=None):
    qs = PaymentEvent.objects.filter(tenant=ctx.tenant)
    if contact_id:
        qs = qs.filter(contact_id=contact_id)
    if opportunity_id:
        qs = qs.filter(opportunity_id=opportunity_id)
    rows = [
        {
            "id": p.id, "ref": p.external_ref, "amount": float(p.amount),
            "status": p.status, "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "match_reason": p.match_reason,
        }
        for p in qs[:20]
    ]
    unresolved = [r for r in rows if r["status"] != PaymentEvent.Status.MATCHED]
    return {
        "payments": rows, "unresolved": len(unresolved),
        "summary": f"{len(rows)} payment(s), {len(unresolved)} unresolved",
    }


@tool(
    "deal_room_engagement",
    "Report how the buyer is interacting with a deal's shared room: opens, distinct devices, "
    "when they last looked, and whether they accepted.",
    {"opportunity_id": {"type": "integer"}},
    ["opportunity_id"],
)
def deal_room_engagement(ctx, opportunity_id):
    from .. import dealroom

    room = DealRoom.objects.filter(tenant=ctx.tenant, opportunity_id=opportunity_id).first()
    if room is None:
        return {"exists": False, "summary": "no deal room has been shared for this deal"}
    state, label = dealroom.engagement_label(room)
    stats = dealroom.engagement(room)
    return {
        "exists": True, "state": state, "label": label,
        **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in stats.items()},
        "summary": label,
    }


@tool(
    "field_trust",
    "Report how much each field of a record can still be believed: what confirmed it, how long "
    "ago, and which fields have decayed past the point of being usable.",
    {
        "subject_type": {"type": "string", "enum": ["contact", "account"]},
        "subject_id": {"type": "integer"},
    },
    ["subject_type", "subject_id"],
)
def field_trust(ctx, subject_type, subject_id):
    subject = ledger.resolve_subject(ctx.tenant, subject_type, subject_id)
    if subject is None:
        return {"error": "subject not found"}
    report = trust.trust_report(subject, subject_type)
    return {
        "score": report["score"], "band": report["band"],
        "fields": [
            {
                "field": f["field"], "state": f["state"], "confidence": f["confidence"],
                "explanation": f["explanation"],
            }
            for f in report["fields"]
        ],
        "summary": (
            f"trust {report['score']}/100 — "
            f"{len(report['problems'])} field(s) missing or stale"
        ),
    }


@tool(
    "list_followups",
    "List open follow-up tasks in this instance, soonest first, so you do not create work that "
    "already exists.",
    {"contact_id": {"type": "integer"}, "limit": {"type": "integer"}},
)
def list_followups(ctx, contact_id=None, limit=15):
    qs = Activity.objects.filter(
        tenant=ctx.tenant, type=Activity.Type.TASK, done=False
    ).select_related("contact")
    if contact_id:
        qs = qs.filter(contact_id=contact_id)
    rows = [
        {
            "id": a.id, "contact": a.contact.full_name, "subject": a.subject,
            "due_at": a.due_at.isoformat() if a.due_at else None,
        }
        for a in qs[: int(limit or 15)]
    ]
    return {"followups": rows, "summary": f"{len(rows)} open follow-up(s)"}


# ---------------------------------------------------------------------------
# 14-18: output — the things a human actually reads
# ---------------------------------------------------------------------------
@tool(
    "draft_followup",
    "Create a follow-up task for the rep, with a drafted message. Drafting is not sending — the "
    "rep edits and decides. Say what the follow-up is *for*, not just that it is due.",
    {
        "contact_id": {"type": "integer"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "days": {"type": "integer"},
    },
    ["contact_id", "subject"],
    writes=True,
)
def draft_followup(ctx, contact_id, subject, body="", days=1):
    contact = Contact.objects.filter(tenant=ctx.tenant, pk=contact_id).first()
    if contact is None:
        return {"error": "contact not found"}
    existing = Activity.objects.filter(
        tenant=ctx.tenant, contact=contact, type=Activity.Type.TASK,
        done=False, subject=subject[:200],
    ).first()
    if existing:
        return {
            "activity_id": existing.id, "created": False,
            "summary": "an identical open follow-up already exists — left it alone",
        }
    activity = Activity.objects.create(
        tenant=ctx.tenant, contact=contact, type=Activity.Type.TASK,
        subject=subject[:200], notes=body,
        due_at=timezone.now() + timedelta(days=max(0, min(int(days or 1), 90))),
    )
    return {
        "activity_id": activity.id, "created": True,
        "summary": f"follow-up drafted for {contact.full_name}: {subject[:80]}",
    }


@tool(
    "ask_human",
    "Ask the sales team something you cannot settle from evidence. Use this instead of guessing "
    "— an open question is a better outcome than a plausible wrong answer.",
    {
        "subject_type": {"type": "string", "enum": [s.value for s in Subject]},
        "subject_id": {"type": "integer"},
        "question": {"type": "string"},
        "context": {"type": "string", "description": "What you checked before asking."},
    },
    ["subject_type", "subject_id", "question"],
    writes=True,
)
def ask_human(ctx, subject_type, subject_id, question, context=""):
    q = AgentQuestion.objects.create(
        tenant=ctx.tenant, subject_type=subject_type, subject_id=subject_id,
        question=question, context=context, run=ctx.run,
    )
    return {"question_id": q.id, "summary": f"asked: {question[:100]}"}


@tool(
    "write_brief",
    "Write the short brief a rep reads on the record. Lead with what changed or what you found; "
    "put the reasoning after it. Say plainly when you found nothing.",
    {"brief": {"type": "string"}},
    ["brief"],
    writes=True,
)
def write_brief(ctx, brief):
    if ctx.run is not None:
        ctx.run.brief = brief.strip()
        ctx.run.save(update_fields=["brief"])
    return {"summary": "brief written", "characters": len(brief or "")}


@tool(
    "discard",
    "Record that you considered a lead or an inference and rejected it, with the reason. "
    "The discards are the most useful part of the trail for a sceptical reader.",
    {"what": {"type": "string"}, "why": {"type": "string"}},
    ["what", "why"],
)
def discard(ctx, what, why):
    return {"discarded": what, "why": why, "summary": f"discarded {what}: {why}"}


@tool(
    "recent_evidence",
    "Show what has recently been observed and applied about a record, so you do not re-verify "
    "something that was confirmed last week.",
    {
        "subject_type": {"type": "string", "enum": [s.value for s in Subject]},
        "subject_id": {"type": "integer"},
    },
    ["subject_type", "subject_id"],
)
def recent_evidence(ctx, subject_type, subject_id):
    rows = Evidence.objects.filter(
        tenant=ctx.tenant, subject_type=subject_type, subject_id=subject_id
    )[:20]
    return {
        "evidence": [
            {
                "field": e.field, "value": e.value, "source": e.source,
                "strength": e.strength, "applied": e.applied,
                "observed_at": e.observed_at.isoformat(), "where": e.source_detail,
            }
            for e in rows
        ],
        "summary": f"{len(rows)} prior observation(s) on file",
    }


@tool(
    "qualify_lead_signals",
    "Read a lead's BANT answers and enquiry text and report the signals present — budget, "
    "authority, need and timeline — without changing the rating, which is the rep's call.",
    {"lead_id": {"type": "integer"}},
    ["lead_id"],
)
def qualify_lead_signals(ctx, lead_id):
    lead = Lead.objects.filter(tenant=ctx.tenant, pk=lead_id).first()
    if lead is None:
        return {"error": "lead not found"}
    signals = {
        "budget": lead.bant_budget, "authority": lead.bant_authority,
        "need": lead.bant_need, "timeline": lead.bant_timeline,
    }
    gaps = [name for name, score in signals.items() if not score]
    return {
        "signals": signals, "score": lead.bant_score(), "rating": lead.rating,
        "unanswered": gaps, "message": lead.message[:600],
        "summary": (
            f"BANT {lead.bant_score()}/12"
            + (f"; unanswered: {', '.join(gaps)}" if gaps else "")
        ),
    }
