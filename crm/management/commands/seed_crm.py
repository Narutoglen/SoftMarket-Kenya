from django.core.management.base import BaseCommand

from crm.seed import seed_softmarket_crm


class Command(BaseCommand):
    help = "Seed the white-label CRM core (creates the 'softmarket' tenant + demo data)."

    def handle(self, *args, **options):
        tenant = seed_softmarket_crm()
        self.stdout.write(
            self.style.SUCCESS(
                f"CRM seeded: tenant '{tenant.slug}' ({tenant.name})."
            )
        )
