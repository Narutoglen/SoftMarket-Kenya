"""Idempotent seeding for the white-label CRM core.

Call ``seed_softmarket_crm()`` from a management command, the shell, or a
post-migrate signal. Creates the first tenant instance ('softmarket') plus a
small demo dataset so the pipeline/reporting endpoints return real data.
"""

from .models import (
    Account, Activity, Contact, Lead, Opportunity, Tenant,
    TenantStage, IntegrationConfig,
)
from . import services


# White-label logo (copied into static/img/ by the build). Persisted here so a
# fresh seed reproduces the branded header; force-updated so re-runs fix a
# tenant that was created before the logo was added.
TENANT_LOGO_URL = "/static/img/softmarket-logo.jpg"


def seed_softmarket_crm():
    tenant, _ = Tenant.objects.get_or_create(
        slug="softmarket",
        defaults={
            "name": "SoftMarket Kenya",
            "brand_primary_color": "#6d28d9",
            "brand_accent_color": "#22d3ee",
            "logo_url": TENANT_LOGO_URL,
            "default_lead_owner": "Brian Mukwe",
        },
    )
    # Keep branding current on every run (idempotent).
    if tenant.logo_url != TENANT_LOGO_URL:
        tenant.logo_url = TENANT_LOGO_URL
        tenant.save(update_fields=["logo_url"])

    # Demo account + contacts (the 360 hub).
    acme, _ = Account.objects.get_or_create(
        tenant=tenant, name="Acme Retail Ltd",
        defaults={"industry": "Retail"},
    )
    c1, _ = Contact.objects.get_or_create(
        tenant=tenant, email="mary@acme.co.ke",
        defaults={"first_name": "Mary", "last_name": "Otieno",
                  "phone": "+254711000001", "account": acme,
                  "territory": "nairobi", "lifecycle": Contact.Lifecycle.CUSTOMER},
    )
    c2, _ = Contact.objects.get_or_create(
        tenant=tenant, email="john@acme.co.ke",
        defaults={"first_name": "John", "last_name": "Kamau",
                  "phone": "+254722000002", "account": acme,
                  "territory": "nakuru", "lifecycle": Contact.Lifecycle.LEAD},
    )

    # Demo opportunities spread across pipeline stages.
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Acme POS Integration",
        contact=c1, defaults={"stage": Opportunity.Stage.PROPOSAL,
                              "amount": 350000, "owner": "Brian Mukwe", "order": 0},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Acme Loyalty Module",
        contact=c2, defaults={"stage": Opportunity.Stage.QUALIFICATION,
                              "amount": 180000, "owner": "Tati Shayo", "order": 0},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Acme Inventory Sync",
        contact=c1, defaults={"stage": Opportunity.Stage.PROSPECTING,
                              "amount": 120000, "owner": "Brian Mukwe", "order": 0},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Nakuru Mart Wholesale Rollout",
        contact=c2, defaults={"stage": Opportunity.Stage.NEGOTIATION,
                              "amount": 640000, "owner": "Tati Shayo", "order": 0},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Kisumu Fresh Starter Pack",
        contact=c2, defaults={"stage": Opportunity.Stage.WON,
                              "amount": 90000, "owner": "Tati Shayo", "order": 0},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Mombasa Shelf Audit",
        contact=c1, defaults={"stage": Opportunity.Stage.LOST,
                              "amount": 75000, "owner": "Brian Mukwe", "order": 0},
    )

    # Demo hot lead (will be auto-scored by qualify_lead if created via API;
    # here we set it directly so the seed shows a hot lead immediately).
    Lead.objects.get_or_create(
        tenant=tenant, email="hot@prospect.co.ke",
        defaults={"first_name": "Asha", "last_name": "Mwangi",
                  "company": "Prospect Co", "territory": "nairobi",
                  "bant_budget": 3, "bant_authority": 3,
                  "bant_need": 3, "bant_timeline": 3,
                  "rating": Lead.Rating.HOT, "owner": "Brian Mukwe"},
    )

    # --- Milestone 5: follow-up tasks + a churn candidate ---
    from django.utils import timezone
    from datetime import timedelta
    now = timezone.now()
    # A quiet CUSTOMER with no activity → lands on the churn radar.
    c3, _ = Contact.objects.get_or_create(
        tenant=tenant, email="grace@wanjiru.co.ke",
        defaults={"first_name": "Grace", "last_name": "Wanjiru",
                  "phone": "+254****0003", "account": acme,
                  "territory": "kiambu", "lifecycle": Contact.Lifecycle.CUSTOMER},
    )
    if c3.lifecycle != Contact.Lifecycle.CUSTOMER:
        c3.lifecycle = Contact.Lifecycle.CUSTOMER
        c3.save(update_fields=["lifecycle"])
    # Open follow-up tasks across buckets (overdue / today / upcoming).
    Activity.objects.get_or_create(
        tenant=tenant, contact=c2, type=Activity.Type.TASK,
        subject="Call John re: loyalty module quote",
        defaults={"due_at": now - timedelta(days=2), "notes": "He asked for pricing."},
    )
    Activity.objects.get_or_create(
        tenant=tenant, contact=c2, type=Activity.Type.TASK,
        subject="Send the POS proposal",
        defaults={"due_at": now.replace(hour=15, minute=0, second=0, microsecond=0),
                  "notes": "Include 3-branch pricing."},
    )
    Activity.objects.get_or_create(
        tenant=tenant, contact=c2, type=Activity.Type.TASK,
        subject="Follow up after Nakuru demo",
        defaults={"due_at": now + timedelta(days=3)},
    )
    # Ensure the four integration channel configs exist for this tenant.
    services.ensure_integration_configs(tenant)
    return tenant


def seed_second_tenant():
    """Milestone 6 proof: a SECOND white-label instance, fully isolated + branded.

    Different slug, name, brand colors, pipeline stages, and integration toggles
    from SoftMarket — proving the core is resellable without a code fork.
    """
    from .models import Account as _Account

    tenant, _ = Tenant.objects.get_or_create(
        slug="greenvault",
        defaults={
            "name": "GreenVault Foods",
            "brand_primary_color": "#047857",   # emerald
            "brand_accent_color": "#f59e0b",     # amber
            "logo_url": "",
            "default_lead_owner": "Laurine Achieng",
        },
    )

    # Per-tenant pipeline stages (different from SoftMarket's defaults).
    stage_specs = [
        ("lead", "New Lead", 15, False, False),
        ("qualified", "Qualified", 35, False, False),
        ("quote", "Quote Sent", 60, False, False),
        ("won", "Closed Won", 100, True, False),
        ("lost", "Closed Lost", 0, False, True),
    ]
    for i, (key, label, prob, won, lost) in enumerate(stage_specs):
        TenantStage.objects.update_or_create(
            tenant=tenant, key=key,
            defaults={"label": label, "order": i, "probability": prob,
                      "is_won": won, "is_lost": lost},
        )

    # Integration configs (GreenVault enables M-Pesa + WhatsApp, not eTIMS/offline yet).
    for ch in ["mpesa", "whatsapp", "etims", "offline"]:
        IntegrationConfig.objects.update_or_create(
            tenant=tenant, channel=ch,
            defaults={"enabled": ch in ("mpesa", "whatsapp")},
        )

    # A little isolated demo data so the instance renders non-empty.
    acct, _ = _Account.objects.get_or_create(
        tenant=tenant, name="Nairobi Greens Co", defaults={"industry": "Fresh produce"},
    )
    Contact.objects.get_or_create(
        tenant=tenant, email="peter@nairobigreens.co.ke",
        defaults={"first_name": "Peter", "last_name": "Ouma",
                  "phone": "0700111222", "account": acct,
                  "territory": "nairobi", "lifecycle": Contact.Lifecycle.CUSTOMER},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Supply deal — 12 outlets",
        contact=Contact.objects.get(tenant=tenant, email="peter@nairobigreens.co.ke"),
        defaults={"stage": "quote", "amount": 480000, "owner": "Laurine Achieng"},
    )
    return tenant

