"""The run loop: claim → plan → act → brief → schedule the next look.

This is the part that makes the agent an agent rather than a button. Work is
pulled from the queue on the agent's own clock, and each run leaves three
artefacts behind: the steps it took (including what it decided *not* to do),
the brief a human reads, and — usually — the next task it scheduled for itself
with the reason in words.

Failure handling is deliberately unglamorous. A run that raises marks its task
for a backed-off retry and records the error on the run; after three attempts
the task fails loudly instead of retrying forever, because a task that cannot
succeed is telling you something about the data and hiding it helps nobody.
"""

from django.utils import timezone

from ..models import AgentRun, AgentTask, Contact, Opportunity, Subject
from . import brain, queue, tools


def run_task(task: AgentTask, planner=None) -> AgentRun:
    """Execute one queued task and return its run record."""
    planner = planner or brain.get_planner()
    run = AgentRun.objects.create(
        tenant=task.tenant,
        task=task,
        planner=planner.name,
        model=getattr(planner, "model", ""),
    )
    ctx = tools.ToolContext(tenant=task.tenant, run=run, task=task)

    try:
        usage = planner.run(ctx, task) or {}
        run.input_tokens = usage.get("input_tokens", 0)
        run.output_tokens = usage.get("output_tokens", 0)
        run.status = AgentRun.Status.DONE
        if not run.brief:
            # A planner that never called write_brief still owes the reader a
            # sentence — silence on the Agent tab reads as a broken feature.
            run.brief = (
                f"Reviewed {task.subject_label} and left it unchanged "
                f"({run.steps.count()} checks, nothing worth recording)."
            )
        run.finished_at = timezone.now()
        run.save(update_fields=[
            "status", "brief", "finished_at", "input_tokens", "output_tokens",
        ])
        queue.complete(task)
    except Exception as exc:  # noqa: BLE001 — one bad run must not stop the queue
        run.status = AgentRun.Status.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        queue.fail(task, exc)
    return run


def run_once(tenant=None, limit=1, planner=None):
    """Claim and execute up to ``limit`` due tasks. Returns the runs."""
    planner = planner or brain.get_planner()
    return [run_task(task, planner=planner) for task in queue.claim_due(tenant=tenant, limit=limit)]


def run_now(tenant, kind, subject_type, subject_id, reason="Requested by a user."):
    """Queue a task and run it immediately — the 'Ask the agent' button.

    The task row still exists afterwards, so a manual run appears in the same
    history as a scheduled one. Reps should not have to hold two mental models
    of where a change came from.
    """
    task = queue.schedule(
        tenant=tenant, kind=kind, subject_type=subject_type, subject_id=subject_id,
        reason=reason, due_in_days=0, priority=-5, dedupe=False,
    )
    claimed = queue.claim_due(tenant=tenant, limit=1)
    # Another dispatcher may have taken it in the gap; run ours regardless so
    # the button never appears to do nothing.
    target = next((t for t in claimed if t.pk == task.pk), None) or task
    if target.pk != task.pk:
        queue.complete(task)
    return run_task(target)


# ---------------------------------------------------------------------------
# Sweeps — how work gets onto the queue without anyone asking
# ---------------------------------------------------------------------------
def sweep(tenant):
    """Look over the whole instance and queue what deserves attention.

    Run this nightly. It is the difference between an assistant you have to
    remember to use and one that has already done the reading by morning.
    """
    from .. import trust

    created = []

    # 1. Records whose data has decayed past usefulness.
    created += trust.queue_reverification(tenant, limit=10, threshold=45)

    # 2. Open deals nobody has looked at this week.
    from .. import services

    closed = {s.key for s in services.tenant_stages(tenant) if s.is_won or s.is_lost}
    for opp in Opportunity.objects.filter(tenant=tenant).exclude(stage__in=closed)[:25]:
        created.append(queue.schedule(
            tenant=tenant, kind=AgentTask.Kind.REVIEW_DEAL,
            subject_type=Subject.OPPORTUNITY, subject_id=opp.pk,
            reason="Weekly health check on an open deal.",
            due_in_days=0, by_agent=True,
        ))

    # 3. Contacts the agent has never looked at.
    seen = set(
        AgentTask.objects.filter(tenant=tenant, subject_type=Subject.CONTACT)
        .values_list("subject_id", flat=True)
    )
    for contact in Contact.objects.filter(tenant=tenant).exclude(pk__in=seen)[:25]:
        created.append(queue.schedule(
            tenant=tenant, kind=AgentTask.Kind.RESEARCH_CONTACT,
            subject_type=Subject.CONTACT, subject_id=contact.pk,
            reason="First look at a contact the agent has not read yet.",
            due_in_days=0, by_agent=True,
        ))

    return [task for task in created if task is not None]


def recent_runs(tenant, limit=20):
    return (
        AgentRun.objects.filter(tenant=tenant)
        .select_related("task")
        .prefetch_related("steps")[:limit]
    )


def runs_for_subject(tenant, subject_type, subject_id, limit=10):
    """The Agent tab for one record: its runs, newest first."""
    return (
        AgentRun.objects.filter(
            tenant=tenant, task__subject_type=subject_type, task__subject_id=subject_id
        )
        .select_related("task")
        .prefetch_related("steps")[:limit]
    )
