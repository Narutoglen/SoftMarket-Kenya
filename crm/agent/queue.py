"""The agent's work queue: due-at scheduling with lease-based claiming.

Two decisions worth explaining.

**Due timestamps, not cron.** The agent decides when a record deserves another
look and stores that moment on the task, along with the reason in words. "Check
back after the demo on Tuesday" is a thing a colleague says; ``0 9 * * 2`` is
not, and a rep can neither read nor argue with the second one.

**Leases, not locks held across the run.** A dispatcher claims a task by
stamping its worker id and an expiry inside a short transaction, then releases
the row and does the slow work outside it. On Postgres the claim uses
``FOR UPDATE SKIP LOCKED`` so several dispatchers take disjoint work without
coordinating. SQLite has no ``SKIP LOCKED`` — it serialises writers at the file
level anyway, which is the correct behaviour for a single-machine dev setup —
so the claim degrades to a plain row lock there.

If a worker dies mid-run its lease simply expires and the task becomes
claimable again. There is no reaper process to forget to deploy.
"""

import socket
import os
import uuid
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from ..models import AgentTask

DEFAULT_LEASE_SECONDS = 300


def worker_id() -> str:
    """Identify this dispatcher well enough to debug a stuck lease."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def schedule(
    tenant, kind, subject_type, subject_id, reason="", due_in_days=0,
    due_at=None, priority=0, payload=None, by_agent=False, dedupe=True,
):
    """Put work on the queue.

    ``dedupe`` collapses a repeat request for the same (kind, subject) while an
    identical task is still pending — otherwise a nightly sweep plus an agent
    recheck plus a rep clicking the button gives you three runs that reach the
    same conclusion and bill three times.
    """
    due_at = due_at or (timezone.now() + timedelta(days=due_in_days))
    if dedupe:
        existing = AgentTask.objects.filter(
            tenant=tenant, kind=kind, subject_type=subject_type,
            subject_id=subject_id, status=AgentTask.Status.QUEUED,
        ).first()
        if existing:
            # Keep the earlier of the two due dates; a fresher reason wins.
            changed = []
            if due_at < existing.due_at:
                existing.due_at = due_at
                changed.append("due_at")
            if reason and reason != existing.reason:
                existing.reason = reason
                changed.append("reason")
            if changed:
                existing.save(update_fields=changed + ["updated_at"])
            return existing
    return AgentTask.objects.create(
        tenant=tenant, kind=kind, subject_type=subject_type, subject_id=subject_id,
        reason=reason, due_at=due_at, priority=priority, payload=payload or {},
        scheduled_by_agent=by_agent,
    )


def claim_due(tenant=None, limit=1, lease_seconds=DEFAULT_LEASE_SECONDS, owner=None):
    """Claim up to ``limit`` due tasks and return them, leased to this worker."""
    owner = owner or worker_id()
    now = timezone.now()
    horizon = now + timedelta(seconds=lease_seconds)

    claimable = (
        AgentTask.objects.filter(due_at__lte=now)
        .filter(
            Q(status=AgentTask.Status.QUEUED)
            # A RUNNING task whose lease lapsed belongs to a worker that died.
            | Q(status=AgentTask.Status.RUNNING, lease_expires_at__lt=now)
        )
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lt=now))
    )
    if tenant is not None:
        claimable = claimable.filter(tenant=tenant)

    claimed = []
    with transaction.atomic():
        qs = claimable.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked
        )
        for task in qs.order_by("priority", "due_at", "id")[:limit]:
            task.status = AgentTask.Status.RUNNING
            task.lease_owner = owner
            task.lease_expires_at = horizon
            task.attempts += 1
            task.save(
                update_fields=[
                    "status", "lease_owner", "lease_expires_at", "attempts", "updated_at",
                ]
            )
            claimed.append(task)
    return claimed


def extend_lease(task, lease_seconds=DEFAULT_LEASE_SECONDS):
    task.lease_expires_at = timezone.now() + timedelta(seconds=lease_seconds)
    task.save(update_fields=["lease_expires_at", "updated_at"])
    return task


def complete(task):
    task.status = AgentTask.Status.DONE
    task.lease_owner = ""
    task.lease_expires_at = None
    task.save(update_fields=["status", "lease_owner", "lease_expires_at", "updated_at"])
    return task


def fail(task, error, retry_in_minutes=15):
    """Record the failure and either back off for a retry or give up.

    Giving up is a real outcome, not a bug: a task that has failed three times
    is telling you something about the data, and quietly retrying it forever
    hides that.
    """
    task.last_error = str(error)[:2000]
    task.lease_owner = ""
    task.lease_expires_at = None
    if task.attempts >= task.max_attempts:
        task.status = AgentTask.Status.FAILED
    else:
        task.status = AgentTask.Status.QUEUED
        task.due_at = timezone.now() + timedelta(minutes=retry_in_minutes)
    task.save(
        update_fields=[
            "status", "last_error", "due_at", "lease_owner", "lease_expires_at", "updated_at",
        ]
    )
    return task


def queue_depth(tenant):
    """Queued / running / overdue counts for the agent console."""
    now = timezone.now()
    base = AgentTask.objects.filter(tenant=tenant)
    return {
        "queued": base.filter(status=AgentTask.Status.QUEUED).count(),
        "due_now": base.filter(status=AgentTask.Status.QUEUED, due_at__lte=now).count(),
        "running": base.filter(status=AgentTask.Status.RUNNING).count(),
        "failed": base.filter(status=AgentTask.Status.FAILED).count(),
    }


def upcoming(tenant, limit=20):
    return (
        AgentTask.objects.filter(
            tenant=tenant, status__in=[AgentTask.Status.QUEUED, AgentTask.Status.RUNNING]
        )
        .order_by("due_at")[:limit]
    )
