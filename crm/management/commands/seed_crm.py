"""Seed the default SoftMarket CRM tenant plus demo data for local preview.

Run with::

    python manage.py seed_crm

Idempotent: safe to re-run. Adds a few demo activities so the 360 timeline
has something to show in the front office.
"""

from django.core.management.base import BaseCommand

from crm.seed import seed_softmarket_crm, seed_second_tenant
from crm.models import Activity, Contact


class Command(BaseCommand):
    help = "Seed the default SoftMarket CRM tenant + demo data."

    def handle(self, *args, **options):
        tenant = seed_softmarket_crm()

        # A little timeline data so the 360 view isn't empty in preview.
        mary = Contact.objects.filter(tenant=tenant, email="mary@acme.co.ke").first()
        if mary and not mary.activities.exists():
            Activity.objects.create(
                tenant=tenant, contact=mary, type=Activity.Type.CALL,
                subject="Proposal walkthrough", notes="Discussed POS integration scope.",
            )
            Activity.objects.create(
                tenant=tenant, contact=mary, type=Activity.Type.EMAIL,
                subject="Intro from referral", notes="Opened and replied.",
            )
            Activity.objects.create(
                tenant=tenant, contact=mary, type=Activity.Type.TASK,
                subject="Send pricing sheet", done=False,
            )

        self.stdout.write(self.style.SUCCESS(f"Seeded CRM tenant: {tenant.name}"))
        t2 = seed_second_tenant()
        self.stdout.write(self.style.SUCCESS(f"Seeded 2nd tenant: {t2.name} (slug={t2.slug})"))
