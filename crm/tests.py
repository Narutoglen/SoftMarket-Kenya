"""Tests for the white-label CRM core (Milestones 1-6).

Covers the logic a Zoho-grade CRM must get right: tenant isolation, BANT
scoring + territory routing, lead->contact conversion, the Kanban move, the
follow-up/churn buckets, and the integration enqueue path.

The browser already proves the UI; these tests are the regression net.
"""

from django.test import TestCase, Client
from django.urls import reverse

from .models import (
    Activity, Contact, Lead, Opportunity, Tenant,
    TenantStage, IntegrationConfig, IntegrationMessage,
)
from . import services


def make_tenant(slug="softmarket", **kwargs):
    defaults = {
        "name": "SoftMarket Kenya",
        "brand_primary_color": "#6d28d9",
        "brand_accent_color": "#22d3ee",
        "default_lead_owner": "Brian Mukwe",
    }
    defaults.update(kwargs)
    t, _ = Tenant.objects.get_or_create(slug=slug, defaults=defaults)
    services.ensure_integration_configs(t)
    return t


def client_for(tenant_slug=None):
    """Test client that resolves the tenant via the X-CRM-Instance header."""
    c = Client(SERVER_NAME="127.0.0.1")
    if tenant_slug:
        c.defaults["HTTP_X_CRM_INSTANCE"] = tenant_slug
    return c


class TenantIsolationTests(TestCase):
    def test_tenant_scoping(self):
        a = make_tenant("alpha")
        b = make_tenant("bravo")
        Contact.objects.create(tenant=a, first_name="A", email="a@x.com")
        Contact.objects.create(tenant=b, first_name="B", email="b@x.com")
        self.assertEqual(Contact.objects.filter(tenant=a).count(), 1)
        self.assertEqual(Contact.objects.filter(tenant=b).count(), 1)
        self.assertEqual(Contact.objects.filter(tenant=a).first().first_name, "A")

    def test_default_tenant_is_softmarket(self):
        make_tenant("softmarket")
        other = make_tenant("otherco")
        # request with no instance header resolves to softmarket
        c = Client(SERVER_NAME="127.0.0.1")
        resp = c.get(reverse("crm:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["tenant"].slug, "softmarket")
        Contact.objects.create(tenant=other, first_name="Z", email="z@x.com")
        # softmarket dashboard must NOT show otherco's contact
        self.assertEqual(resp.context["tenant"].contacts.count(), 0)


class BantScoringTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()

    def _lead(self, **kw):
        kw.setdefault("first_name", "Test")
        kw.setdefault("last_name", "User")
        kw.setdefault("email", "test@example.com")
        kw.setdefault("territory", "nairobi")
        return Lead.objects.create(tenant=self.tenant, **kw)

    def test_hot_lead_scores_correctly(self):
        lead = self._lead(
            bant_budget=3, bant_authority=3, bant_need=3, bant_timeline=3,
        )
        services.qualify_lead(lead)
        self.assertEqual(lead.bant_score(), 12)
        self.assertEqual(lead.rating, Lead.Rating.HOT)

    def test_cold_lead_scores_correctly(self):
        lead = self._lead(
            bant_budget=1, bant_authority=1, bant_need=1, bant_timeline=1,
        )
        services.qualify_lead(lead)
        self.assertEqual(lead.bant_score(), 4)
        self.assertEqual(lead.rating, Lead.Rating.COLD)

    def test_routing_by_territory(self):
        lead = self._lead(territory="kisumu")
        self.assertEqual(services.route_lead_owner(self.tenant, lead), "Tati Shayo")
        lead2 = self._lead(territory="nairobi")
        self.assertEqual(services.route_lead_owner(self.tenant, lead2), "Brian Mukwe")

    def test_intake_automates_score_route_response(self):
        lead = self._lead(bant_budget=3, bant_authority=3, bant_need=3, bant_timeline=3)
        services.intake_lead(lead)
        lead.refresh_from_db()
        self.assertEqual(lead.rating, Lead.Rating.HOT)
        self.assertEqual(lead.owner, "Brian Mukwe")
        self.assertTrue(lead.auto_responded)


class ConvertTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()

    def test_convert_creates_contact_and_account(self):
        lead = Lead.objects.create(
            tenant=self.tenant, first_name="Jane", last_name="Doe",
            email="jane@x.com", phone="0700", company="Jane Co",
            territory="nairobi", message="I need a POS.",
        )
        contact = services.convert_lead_to_contact(lead, create_account=True)
        self.assertIsInstance(contact, Contact)
        self.assertEqual(contact.email, "jane@x.com")
        self.assertEqual(contact.account.name, "Jane Co")
        self.assertTrue(
            contact.activities.filter(subject="Original lead inquiry").exists()
        )
        lead.refresh_from_db()
        self.assertEqual(lead.converted_contact, contact)

    def test_convert_is_idempotent(self):
        lead = Lead.objects.create(
            tenant=self.tenant, first_name="Jane", last_name="Doe", email="jane@x.com",
        )
        c1 = services.convert_lead_to_contact(lead)
        c2 = services.convert_lead_to_contact(lead)
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(Contact.objects.filter(tenant=self.tenant).count(), 1)


class PipelineTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()
        self.stages = services.tenant_stages(self.tenant)
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="P", email="p@x.com",
        )

    def test_tenant_stages_default_fallback(self):
        # brand-new tenant with no TenantStage rows still gets a board
        fresh = make_tenant("freshco")
        TenantStage.objects.filter(tenant=fresh).delete()
        stages = services.tenant_stages(fresh)
        self.assertEqual(len(stages), 6)
        self.assertTrue(any(s.is_won for s in stages))
        self.assertTrue(any(s.is_lost for s in stages))

    def test_pipeline_move_updates_stage(self):
        opp = Opportunity.objects.create(
            tenant=self.tenant, name="Deal", contact=self.contact,
            stage="prospecting", amount=100000, owner="Brian",
        )
        won_key = next(s.key for s in self.stages if s.is_won)
        c = client_for()
        resp = c.post(
            reverse("crm:opportunity_move", args=[opp.pk]),
            {"stage": won_key}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        opp.refresh_from_db()
        self.assertEqual(opp.stage, won_key)


class FollowupChurnTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="Q", email="q@x.com",
            lifecycle=Contact.Lifecycle.CUSTOMER,
        )

    def test_overdue_bucket(self):
        from django.utils import timezone
        from datetime import timedelta
        Activity.objects.create(
            tenant=self.tenant, contact=self.contact, type=Activity.Type.TASK,
            subject="Overdue", due_at=timezone.now() - timedelta(days=2),
        )
        buckets = services.followup_buckets(self.tenant)
        self.assertEqual(len(buckets["overdue"]), 1)
        self.assertEqual(len(buckets["today"]), 0)

    def test_churn_flags_quiet_customer(self):
        # No activity at all -> churn candidate
        churn = services.churn_candidates(self.tenant)
        self.assertTrue(churn)
        self.assertEqual(churn[0]["contact"], self.contact)


class IntegrationTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()

    def test_enqueue_creates_tenant_scoped_message(self):
        msg = services.enqueue_integration_message(
            self.tenant, "mpesa", "0712345678", payload={"demo": True},
        )
        self.assertEqual(msg.status, IntegrationMessage.Status.PENDING)
        self.assertEqual(msg.tenant, self.tenant)
        self.assertEqual(IntegrationMessage.objects.filter(tenant=self.tenant).count(), 1)

    def test_integration_configs_per_tenant(self):
        t2 = make_tenant("secondco")
        self.assertEqual(IntegrationConfig.objects.filter(tenant=self.tenant).count(), 4)
        self.assertEqual(IntegrationConfig.objects.filter(tenant=t2).count(), 4)

    def test_send_endpoint_enqueues(self):
        c = client_for()
        resp = c.post(
            reverse("crm:integration_send"),
            {"channel": "whatsapp", "recipient": "0712345678"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            IntegrationMessage.objects.filter(tenant=self.tenant).count(), 1
        )


class SecondTenantPreviewTests(TestCase):
    """M6 done-when: a second tenant renders isolated + branded in the UI."""

    def test_greenvault_dashboard_isolated(self):
        sm = make_tenant("softmarket")
        gv = make_tenant("greenvault", name="GreenVault Foods",
                         brand_primary_color="#047857")
        Contact.objects.create(tenant=sm, first_name="S", email="s@x.com")
        Contact.objects.create(tenant=gv, first_name="G", email="g@x.com")
        c = client_for("greenvault")
        resp = c.get(reverse("crm:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["tenant"].slug, "greenvault")
        # only GreenVault's own contact counts
        self.assertEqual(resp.context["tenant"].contacts.count(), 1)
        self.assertContains(resp, "GreenVault Foods")


class PublicIntakeRobustnessTests(TestCase):
    """The public intake endpoints must degrade gracefully on garbage input."""

    def setUp(self):
        self.tenant = make_tenant()

    def test_garbage_bant_values_do_not_500(self):
        c = client_for()
        resp = c.post(reverse("crm:lead_intake_api"), {
            "first_name": "Garbage", "email": "g@x.com",
            "bant_budget": "lots", "bant_authority": "9999",
            "bant_need": "", "bant_timeline": "2.5",
        })
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get(email="g@x.com")
        self.assertEqual(lead.bant_budget, 0)      # "lots" -> default
        self.assertEqual(lead.bant_authority, 3)   # 9999 -> clamped to 3
        self.assertEqual(lead.bant_timeline, 0)    # "2.5" is not an int

    def test_invalid_due_at_returns_400_not_500(self):
        contact = Contact.objects.create(
            tenant=self.tenant, first_name="D", email="d@x.com",
        )
        c = client_for()
        resp = c.post(
            reverse("crm:activity_create_api", args=[contact.pk]),
            {"subject": "Call", "due_at": "not-a-date"},
        )
        self.assertEqual(resp.status_code, 400)
        resp = c.post(
            reverse("crm:activity_create_api", args=[contact.pk]),
            {"subject": "Call", "due_at": "2026-08-01T10:00:00"},
        )
        self.assertEqual(resp.status_code, 201)

    def test_settings_save_bad_probability_does_not_500(self):
        c = client_for()
        resp = c.post(reverse("crm:crm_settings_save"), {
            "name": self.tenant.name,
            "brand_primary_color": "#6d28d9",
            "brand_accent_color": "#22d3ee",
            "logo_url": "",
            "stage_key_0": "proposal",
            "stage_label_0": "Proposal",
            "stage_prob_0": "not-a-number",
        })
        self.assertEqual(resp.status_code, 302)
        stage = TenantStage.objects.get(tenant=self.tenant, key="proposal")
        self.assertEqual(stage.probability, 50)
