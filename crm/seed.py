"""Idempotent seeding for the white-label CRM core.

Call ``seed_softmarket_crm()`` from a management command, the shell, or a
post-migrate signal. Creates the first tenant instance ('softmarket') plus a
small demo dataset so the pipeline/reporting endpoints return real data.
"""

from .models import Account, Contact, Lead, Opportunity, Tenant


def seed_softmarket_crm():
    tenant, _ = Tenant.objects.get_or_create(
        slug="softmarket",
        defaults={
            "name": "SoftMarket Kenya",
            "brand_primary_color": "#6d28d9",
            "brand_accent_color": "#22d3ee",
            "default_lead_owner": "Brian Mukwe",
        },
    )

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

    # Demo opportunities in the pipeline.
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Acme POS Integration",
        contact=c1, defaults={"stage": Opportunity.Stage.PROPOSAL,
                              "amount": 350000, "owner": "Brian Mukwe"},
    )
    Opportunity.objects.get_or_create(
        tenant=tenant, name="Acme Loyalty Module",
        contact=c2, defaults={"stage": Opportunity.Stage.QUALIFICATION,
                              "amount": 180000, "owner": "Tati Shayo"},
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
    return tenant
