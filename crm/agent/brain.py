"""The planner: Claude when it is configured, a deterministic playbook when not.

Both planners drive the *same* tool registry, so the guard rails, the tenant
scoping and the audit trail are identical whichever one ran. What differs is
only how the next tool call is chosen: Claude reads the skills and decides, the
playbook follows a fixed sequence per task kind. That split is what keeps the
system honest — the interesting behaviour lives in the evidence ledger and the
tools, not in the model, so a deployment with no API key is a fully working CRM
agent rather than a stub.

The loop here is written by hand rather than using the SDK's tool runner. The
reason is the shared executor: every tool call has to be persisted as an
``AgentStep`` row against the run, inside the same dispatch path the playbook
uses, and the loop needs a hard step ceiling per run. Owning the loop keeps
those invariants in one place instead of split across a helper's callbacks.
"""

import json
import os
from pathlib import Path

from django.conf import settings

from . import tools

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Read the whole task spec up front and let the model work — the guidance in
# the skills files is written as principles, not step-by-step choreography.
MODEL = getattr(settings, "CRM_AGENT_MODEL", "claude-opus-5")
MAX_STEPS = getattr(settings, "CRM_AGENT_MAX_STEPS", 14)
MAX_TOKENS = 16000


def load_skills() -> str:
    """Concatenate the versioned markdown skills into the system prompt.

    They are files, not string literals, so they can be reviewed, diffed and
    argued about like any other governing document — which is what they are.
    """
    parts = []
    for name in ("evidence.md", "identity-matching.md", "data-boundaries.md",
                 "writing-a-brief.md"):
        path = SKILLS_DIR / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def is_configured() -> bool:
    """True when an Anthropic credential and the SDK are both available."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def system_prompt(tenant, task) -> str:
    subject = f"{task.get_subject_type_display()} #{task.subject_id} ({task.subject_label})"
    return (
        f"You are the research agent inside {tenant.name}'s CRM. You work on your own "
        "queue, on your own schedule, and the sales team reads what you leave behind.\n\n"
        f"This run is about: {subject}.\n"
        f"Task kind: {task.get_kind_display()}.\n"
        f"Why it was queued: {task.reason or 'routine review'}.\n\n"
        "Work from what the CRM already contains before reaching for anything else — most "
        "questions are answered in the timeline. Submit what you observe through record_fact "
        "and let the ledger decide what it earns. Finish every run by calling write_brief, "
        "even when the answer is that nothing changed, and schedule_recheck when the record "
        "will be worth another look.\n\n"
        "The following skills govern how you work. They are not suggestions.\n\n"
        f"{load_skills()}"
    )


class ClaudePlanner:
    """Plans the run with Claude, executing tools through the shared registry."""

    name = "claude"

    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = MODEL

    def run(self, ctx: tools.ToolContext, task) -> dict:
        messages = [{
            "role": "user",
            "content": (
                "Work this task. Read the record first, then act only on what you can source."
            ),
        }]
        tool_defs = tools.schemas()
        usage = {"input_tokens": 0, "output_tokens": 0}

        for _ in range(MAX_STEPS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system_prompt(ctx.tenant, task),
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                tools=tool_defs,
                messages=messages,
            )
            usage["input_tokens"] += getattr(response.usage, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(response.usage, "output_tokens", 0) or 0

            # Safety classifiers can decline; check before reading content.
            if response.stop_reason == "refusal":
                return {**usage, "stopped": "refusal"}
            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                output = tools.call(ctx, block.name, **(block.input or {}))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, default=str)[:6000],
                    "is_error": "error" in output,
                })
            if not results:
                break
            messages.append({"role": "user", "content": results})

        return {**usage, "stopped": "done"}


class PlaybookPlanner:
    """The deterministic path: a fixed tool sequence per task kind.

    Not a fallback in the apologetic sense. Most of these jobs — re-verify a
    stale phone number, look at why a deal has gone quiet — have one sensible
    order of operations, and running it as code is cheaper, faster and
    perfectly auditable. The model earns its place on the ambiguous ones.
    """

    name = "playbook"

    def run(self, ctx: tools.ToolContext, task) -> dict:
        from ..models import AgentTask

        handler = {
            AgentTask.Kind.RESEARCH_CONTACT: self._research_contact,
            AgentTask.Kind.VERIFY_FIELD: self._verify_field,
            AgentTask.Kind.ENRICH_ACCOUNT: self._enrich_account,
            AgentTask.Kind.REVIEW_DEAL: self._review_deal,
            AgentTask.Kind.DEAL_ROOM_SIGNAL: self._deal_room_signal,
            AgentTask.Kind.RECONCILE_PAYMENT: self._reconcile_payment,
            AgentTask.Kind.BRIEF: self._brief_only,
        }.get(task.kind, self._brief_only)
        handler(ctx, task)
        return {"input_tokens": 0, "output_tokens": 0, "stopped": "done"}

    # -- handlers ----------------------------------------------------------
    def _research_contact(self, ctx, task):
        sid = task.subject_id
        history = tools.call(ctx, "read_crm_history", subject_type="contact", subject_id=sid)
        signatures = tools.call(ctx, "extract_signature_block", contact_id=sid)
        applied, suggested = [], []
        for obs in signatures.get("observations", []):
            outcome = tools.call(
                ctx, "record_fact", subject_type="contact", subject_id=sid,
                field=obs["field"], value=obs["value"], source=obs["source"],
                source_detail=obs["where"],
            )
            if outcome.get("outcome") == "applied":
                applied.append(obs["field"])
            elif outcome.get("outcome") == "suggested":
                suggested.append(obs["field"])

        duplicates = tools.call(ctx, "flag_duplicate", contact_id=sid)
        trust_row = tools.call(ctx, "field_trust", subject_type="contact", subject_id=sid)

        lines = []
        if applied:
            lines.append(f"Updated {', '.join(applied)} from a signature block on file.")
        if suggested:
            lines.append(f"Proposed a change to {', '.join(suggested)} for someone to confirm.")
        if duplicates.get("candidates"):
            names = ", ".join(c["name"] for c in duplicates["candidates"][:3])
            lines.append(f"Possible duplicate record(s): {names}.")
        if not lines:
            lines.append(
                f"Read {history.get('activity_count', 0)} activities and found nothing new to "
                "record."
            )
        lines.append(
            f"Trust score is now {trust_row.get('score', 0)}/100."
        )
        tools.call(ctx, "write_brief", brief=" ".join(lines))
        tools.call(
            ctx, "schedule_recheck", subject_type="contact", subject_id=sid, days=30,
            reason="Routine 30-day check that the contact details still hold.",
        )

    def _verify_field(self, ctx, task):
        sid, stype = task.subject_id, task.subject_type
        fields = (task.payload or {}).get("fields", [])
        trust_row = tools.call(ctx, "field_trust", subject_type=stype, subject_id=sid)
        found = []
        if stype == "contact":
            signatures = tools.call(ctx, "extract_signature_block", contact_id=sid)
            for obs in signatures.get("observations", []):
                if fields and obs["field"] not in fields:
                    continue
                outcome = tools.call(
                    ctx, "record_fact", subject_type="contact", subject_id=sid,
                    field=obs["field"], value=obs["value"], source=obs["source"],
                    source_detail=obs["where"],
                )
                found.append(f"{obs['field']} → {obs['value']} ({outcome.get('outcome')})")
        elif stype == "account":
            enrichment = tools.call(ctx, "enrich_company", account_id=sid)
            for obs in enrichment.get("observations", []):
                outcome = tools.call(
                    ctx, "record_fact", subject_type="account", subject_id=sid,
                    field=obs["field"], value=obs["value"], source=obs["source"],
                    source_detail=obs["where"],
                )
                found.append(f"{obs['field']} → {obs['value']} ({outcome.get('outcome')})")

        stale = ", ".join(fields) or "several fields"
        if found:
            brief = (
                f"Re-checked {stale}. From evidence already in the CRM: {'; '.join(found)}. "
                f"Trust score is now {trust_row.get('score', 0)}/100."
            )
        else:
            brief = (
                f"{stale.capitalize()} could not be confirmed from anything in the CRM — there "
                "is no signature block, form submission or payment carrying it. Someone needs "
                "to ask the customer directly."
            )
            tools.call(
                ctx, "ask_human", subject_type=stype, subject_id=sid,
                question=f"Can someone confirm {stale} on the next call?",
                context="No source in the CRM carries this field, so it cannot be verified here.",
            )
        tools.call(ctx, "write_brief", brief=brief)

    def _enrich_account(self, ctx, task):
        sid = task.subject_id
        enrichment = tools.call(ctx, "enrich_company", account_id=sid)
        outcomes = []
        for obs in enrichment.get("observations", []):
            outcome = tools.call(
                ctx, "record_fact", subject_type="account", subject_id=sid,
                field=obs["field"], value=obs["value"], source=obs["source"],
                source_detail=obs["where"],
            )
            outcomes.append(f"{obs['value']} ({outcome.get('outcome')})")
        for row in enrichment.get("discarded", []):
            tools.call(ctx, "discard", what=row["domain"], why=row["why"])
        brief = (
            "Derived the company domain from staff email addresses: " + "; ".join(outcomes)
            if outcomes
            else "No work email addresses on file, so there is nothing to derive the company "
                 "domain from yet."
        )
        tools.call(ctx, "write_brief", brief=brief)

    def _review_deal(self, ctx, task):
        sid = task.subject_id
        health = tools.call(ctx, "assess_deal", opportunity_id=sid)
        if "error" in health:
            tools.call(ctx, "write_brief", brief="The deal no longer exists in this instance.")
            return
        payments = tools.call(ctx, "check_payments", opportunity_id=sid)
        risks = health.get("risks", [])
        deal = health.get("deal", {})
        if risks:
            brief = f"{deal.get('name')} has {len(risks)} thing(s) working against it: " + \
                    "; ".join(risks) + "."
            contact_id = self._contact_for_deal(ctx, sid)
            if contact_id:
                tools.call(
                    ctx, "draft_followup", contact_id=contact_id,
                    subject=f"Unstick {deal.get('name')}",
                    body=(
                        "Raised because: " + "; ".join(risks) + ".\n\n"
                        "Suggested opener: ask what would have to be true for this to move this "
                        "month, rather than asking for an update."
                    ),
                    days=1,
                )
        else:
            brief = f"{deal.get('name')} is moving normally; nothing needs doing."
        if payments.get("unresolved"):
            brief += f" {payments['unresolved']} payment(s) against it still need confirming."
        tools.call(ctx, "write_brief", brief=brief)
        tools.call(
            ctx, "schedule_recheck", subject_type="opportunity", subject_id=sid,
            kind="review_deal", days=7,
            reason="Weekly health check while the deal is open.",
        )

    def _deal_room_signal(self, ctx, task):
        sid = task.subject_id
        engagement = tools.call(ctx, "deal_room_engagement", opportunity_id=sid)
        contact_id = self._contact_for_deal(ctx, sid)
        if contact_id and engagement.get("state") == "hot":
            tools.call(
                ctx, "draft_followup", contact_id=contact_id,
                subject="Answer the question the quote has not answered",
                body=(
                    f"{engagement.get('label')}. Re-reading without replying usually means one "
                    "specific thing is unresolved — price, timing, or who signs. Ask which."
                ),
                days=0,
            )
        tools.call(
            ctx, "write_brief",
            brief=(
                f"Deal room activity: {engagement.get('label', 'no room shared')}. "
                + ("Drafted a nudge for the rep." if contact_id else "")
            ),
        )

    def _reconcile_payment(self, ctx, task):
        payment_id = (task.payload or {}).get("payment_id")
        payments = tools.call(ctx, "check_payments", contact_id=task.subject_id)
        row = next(
            (p for p in payments.get("payments", []) if p["id"] == payment_id), None
        )
        if row is None:
            tools.call(ctx, "write_brief", brief="That payment has already been resolved.")
            return
        tools.call(
            ctx, "ask_human", subject_type="contact", subject_id=task.subject_id,
            question=(
                f"KSh {row['amount']:,.0f} came in (ref {row['ref'] or 'n/a'}) — which deal "
                "does it belong to?"
            ),
            context=row.get("match_reason", ""),
        )
        tools.call(
            ctx, "write_brief",
            brief=(
                f"A payment of KSh {row['amount']:,.0f} could not be attributed with confidence. "
                f"{row.get('match_reason', '')} Left it for a human rather than guessing."
            ),
        )

    def _brief_only(self, ctx, task):
        history = tools.call(
            ctx, "read_crm_history", subject_type=task.subject_type, subject_id=task.subject_id
        )
        tools.call(
            ctx, "write_brief",
            brief=(
                f"Reviewed {task.subject_label}: "
                f"{history.get('activity_count', 0)} activities on file. Nothing to action."
            ),
        )

    @staticmethod
    def _contact_for_deal(ctx, opportunity_id):
        from ..models import Opportunity

        opp = Opportunity.objects.filter(tenant=ctx.tenant, pk=opportunity_id).first()
        return opp.contact_id if opp else None


def get_planner():
    """Claude if it is available and enabled, otherwise the playbook."""
    if getattr(settings, "CRM_AGENT_USE_LLM", True) and is_configured():
        try:
            return ClaudePlanner()
        except Exception:  # noqa: BLE001 — a broken client must not stop the queue
            return PlaybookPlanner()
    return PlaybookPlanner()
