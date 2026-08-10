"""Drive the CRM agent from the command line or a scheduler.

    python manage.py run_agent --sweep            # queue tonight's work
    python manage.py run_agent --once --limit 5   # drain up to five due tasks
    python manage.py run_agent --loop             # stay up and keep draining

``--once`` is the shape you want behind cron or a serverless schedule;
``--loop`` is for a worker dyno. Several of either can run against one database
safely — claiming is lease-based (see ``crm/agent/queue.py``).
"""

import time

from django.core.management.base import BaseCommand

from crm.agent import brain, queue, runner
from crm.models import Tenant


class Command(BaseCommand):
    help = "Run the CRM research agent's work queue."

    def add_arguments(self, parser):
        parser.add_argument("--instance", help="Tenant slug. Omit to serve every tenant.")
        parser.add_argument("--sweep", action="store_true",
                            help="Queue work (decayed records, open deals, unseen contacts).")
        parser.add_argument("--once", action="store_true", help="Drain due tasks, then exit.")
        parser.add_argument("--loop", action="store_true", help="Keep draining until stopped.")
        parser.add_argument("--limit", type=int, default=5, help="Tasks per pass.")
        parser.add_argument("--interval", type=int, default=30,
                            help="Seconds between passes in --loop mode.")

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(active=True)
        if options["instance"]:
            tenants = tenants.filter(slug=options["instance"])
        tenants = list(tenants)
        if not tenants:
            self.stderr.write(self.style.ERROR("No matching active tenant."))
            return

        planner = brain.get_planner()
        self.stdout.write(f"Planner: {planner.name}"
                          + (f" ({getattr(planner, 'model', '')})" if planner.name == "claude" else ""))

        if options["sweep"]:
            for tenant in tenants:
                queued = runner.sweep(tenant)
                self.stdout.write(
                    self.style.SUCCESS(f"[{tenant.slug}] queued {len(queued)} task(s)")
                )

        if options["loop"]:
            self.stdout.write("Draining continuously — Ctrl-C to stop.")
            try:
                while True:
                    if not self._pass(tenants, options["limit"], planner):
                        time.sleep(options["interval"])
            except KeyboardInterrupt:
                self.stdout.write("\nStopped.")
            return

        if options["once"] or not options["sweep"]:
            self._pass(tenants, options["limit"], planner)

        for tenant in tenants:
            depth = queue.queue_depth(tenant)
            self.stdout.write(
                f"[{tenant.slug}] queued={depth['queued']} due={depth['due_now']} "
                f"running={depth['running']} failed={depth['failed']}"
            )

    def _pass(self, tenants, limit, planner):
        did_work = False
        for tenant in tenants:
            for run in runner.run_once(tenant=tenant, limit=limit, planner=planner):
                did_work = True
                style = self.style.SUCCESS if run.status == run.Status.DONE else self.style.ERROR
                subject = run.task.subject_label if run.task else "—"
                self.stdout.write(style(
                    f"[{tenant.slug}] {run.task.kind if run.task else '?'} → {subject}: "
                    f"{run.brief or run.error}"
                ))
        return did_work
