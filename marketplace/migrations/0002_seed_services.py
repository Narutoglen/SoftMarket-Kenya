from django.db import migrations


SERVICES = [
    ("Business website", "business-website", 20_000, 80_000, 2_000, False),
    ("Ecommerce website", "ecommerce-website", 50_000, 500_000, 5_000, False),
    ("Web app", "web-app", 100_000, 600_000, 5_000, False),
    ("Android app", "android-app", 80_000, 500_000, 10_000, False),
    ("Cross-platform app", "cross-platform-app", 150_000, 800_000, 10_000, False),
    ("Business system", "business-system", 150_000, 1_000_000, 10_000, False),
    ("Maintenance/support", "maintenance-support", 5_000, 30_000, 2_000, True),
]


def seed_services(apps, schema_editor):
    ServiceCategory = apps.get_model("marketplace", "ServiceCategory")
    for name, slug, min_price, max_price, deposit, monthly in SERVICES:
        ServiceCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": f"{name} service package",
                "min_price": min_price,
                "max_price": max_price,
                "deposit_amount": deposit,
                "monthly": monthly,
                "active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_services, migrations.RunPython.noop),
    ]
