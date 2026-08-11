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
            "is_public": True,
        },
    )
    # Keep branding current on every run (idempotent).
    if tenant.logo_url != TENANT_LOGO_URL:
        tenant.logo_url = TENANT_LOGO_URL
        tenant.save(update_fields=["logo_url"])
    # Force the public flag so the marketing site stays open (plan a).
    if not tenant.is_public:
        tenant.is_public = True
        tenant.save(update_fields=["is_public"])

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

    # --- M7+: give the agent, the trust radar and the deal room something real
    # to work with. Without this the demo shows empty states, which reads as
    # broken rather than as clean.
    _seed_agent_fodder(tenant, acme, c1, c2, c3)
    return tenant


def _seed_agent_fodder(tenant, account, mary, john, grace):
    """Demo material for the agentic layer.

    Deliberately *imperfect* data: a signature block the agent can mine, an
    account with no website, and a contact nobody has confirmed in years. A
    seed where everything is already correct proves nothing.
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import DealRoom, IntegrationConfig, Opportunity

    # A logged email carrying a signature block — the agent's raw material.
    Activity.objects.get_or_create(
        tenant=tenant, contact=john, type=Activity.Type.EMAIL,
        subject="Re: Loyalty module pricing",
        defaults={"notes": (
            "Thanks for sending this through — the three-branch option works for us.\n"
            "Can you confirm the rollout dates?\n\n"
            "Regards,\n"
            "John Kamau\n"
            "Procurement Manager\n"
            "Acme Retail Ltd\n"
            "+254 722 000 002\n"
        )},
    )

    # A contact who has gone stale: created long ago, never confirmed since.
    Contact.objects.filter(pk=grace.pk).update(
        created_at=timezone.now() - timedelta(days=900)
    )

    # Close dates so the deal review has something honest to forecast.
    for offset, name in ((14, "Acme POS Integration"), (30, "Nakuru Mart Wholesale Rollout")):
        Opportunity.objects.filter(tenant=tenant, name=name, expected_close_date=None).update(
            expected_close_date=(timezone.now() + timedelta(days=offset)).date()
        )

    # M-Pesa switched on with a paybill, so deal rooms can show how to pay and
    # the reconciliation engine has somewhere to send people.
    IntegrationConfig.objects.update_or_create(
        tenant=tenant, channel=IntegrationConfig.Channel.MPESA,
        defaults={
            "enabled": True,
            "config_json": {
                "paybill": "247247",
                "account_hint": "Use the quote reference as the account number",
            },
        },
    )

    # A deal room already shared with the buyer.
    proposal = Opportunity.objects.filter(tenant=tenant, name="Acme POS Integration").first()
    if proposal and not hasattr(proposal, "deal_room"):
        DealRoom.objects.get_or_create(
            tenant=tenant, opportunity=proposal,
            defaults={
                "headline": "POS integration for Acme Retail",
                "summary": (
                    "Hi Mary — everything for the POS rollout in one place: what is included, "
                    "what it costs, and how to get started."
                ),
                "line_items": [
                    {"label": "POS integration (3 branches)", "qty": 3, "unit_price": 90000},
                    {"label": "Staff training + go-live support", "qty": 1, "unit_price": 80000},
                ],
                "terms": "50% to begin, balance on go-live. Includes 3 months of support.",
                "next_step": "Accept to lock in the February install slot.",
            },
        )
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
            "is_public": False,
        },
    )
    # Force private on every run so the auth gate stays in effect (auth is
    # per-user via TenantMembership, no shared code needed).
    if tenant.is_public:
        tenant.is_public = False
        tenant.save(update_fields=["is_public"])

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

