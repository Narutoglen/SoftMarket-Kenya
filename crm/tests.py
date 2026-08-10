"""Tests for the white-label CRM core (Milestones 1-6) and the agentic layer (M7+).

Covers the logic a Zoho-grade CRM must get right: tenant isolation, BANT
scoring + territory routing, lead->contact conversion, the Kanban move, the
follow-up/churn buckets, and the integration enqueue path.

For the agentic layer the tests concentrate on the rules that must never bend:
weak evidence cannot write to a record, judgement fields are off-limits to the
agent entirely, a rejected suggestion is not re-proposed, and a replayed M-Pesa
confirmation cannot book revenue twice.

The browser already proves the UI; these tests are the regression net.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .models import (
    Activity, AgentQuestion, AgentRun, AgentTask, Contact, DealRoom, Evidence,
    Lead, Opportunity, PaymentEvent, Subject, Suggestion, Tenant,
    TenantStage, IntegrationConfig, IntegrationMessage,
)
from . import dealroom, payments, services, trust
from .agent import evidence as ledger
from .agent import queue as agent_queue
from .agent import runner as agent_runner
from .agent import tools as agent_tools


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


# ---------------------------------------------------------------------------
# M7 — the agentic layer
# ---------------------------------------------------------------------------
class EvidenceLedgerTests(TestCase):
    """The rules that stop the agent inventing facts about customers."""

    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="Mary", last_name="Otieno",
            email="mary@acme.co.ke",
        )

    def _record(self, field, value, source, **kw):
        return ledger.record_observation(
            self.tenant, Subject.CONTACT, self.contact.pk, field, value, source, **kw
        )

    def test_strong_source_writes_to_a_blank_field(self):
        out = self._record("phone", "+254711000111", "crm.signature-block")
        self.contact.refresh_from_db()
        self.assertEqual(out["outcome"], "applied")
        self.assertEqual(self.contact.phone, "+254711000111")

    def test_weak_source_becomes_a_suggestion_not_a_write(self):
        out = self._record("job_title", "Procurement Lead", "crm.activity-text")
        self.contact.refresh_from_db()
        self.assertEqual(out["outcome"], "suggested")
        self.assertEqual(self.contact.job_title, "")
        self.assertEqual(Suggestion.objects.filter(tenant=self.tenant).count(), 1)

    def test_a_guess_is_worth_nothing(self):
        """The whole design rests on this: recall can never reach a record."""
        out = self._record("phone", "+254700000000", "model.guess")
        self.contact.refresh_from_db()
        self.assertEqual(out["outcome"], "discarded")
        self.assertEqual(self.contact.phone, "")
        self.assertFalse(Suggestion.objects.filter(tenant=self.tenant).exists())

    def test_judgement_fields_are_refused_outright(self):
        out = self._record("lifecycle", "customer", "crm.payment-confirmation")
        self.contact.refresh_from_db()
        self.assertEqual(out["outcome"], "discarded")
        self.assertIn("judgement", out["reason"])
        self.assertEqual(self.contact.lifecycle, Contact.Lifecycle.SUBSCRIBER)

    def test_a_human_entry_is_not_overwritten_by_a_middling_source(self):
        self.contact.phone = "+254722000222"
        self.contact.save()
        out = self._record("phone", "+254733000333", "crm.email-domain")
        self.contact.refresh_from_db()
        self.assertEqual(out["outcome"], "suggested")
        self.assertEqual(self.contact.phone, "+254722000222")

    def test_a_matching_observation_confirms_rather_than_rewrites(self):
        self.contact.phone = "+254711000111"
        self.contact.save()
        out = self._record("phone", "+254711000111", "crm.payment-confirmation")
        self.assertEqual(out["outcome"], "confirmed")
        self.assertTrue(
            Evidence.objects.filter(tenant=self.tenant, field="phone", applied=True).exists()
        )

    def test_one_pending_suggestion_per_change_however_often_it_runs(self):
        for _ in range(3):
            self._record("job_title", "Procurement Lead", "crm.activity-text")
        self.assertEqual(
            Suggestion.objects.filter(
                tenant=self.tenant, status=Suggestion.Status.PENDING
            ).count(),
            1,
        )

    def test_a_rejected_change_is_not_proposed_again(self):
        self._record("job_title", "Procurement Lead", "crm.activity-text")
        suggestion = Suggestion.objects.get(tenant=self.tenant)
        ledger.reject_suggestion(suggestion, decided_by="tester")
        out = self._record("job_title", "Procurement Lead", "crm.activity-text")
        self.assertEqual(out["outcome"], "discarded")
        self.assertIn("rejected", out["reason"])

    def test_accepting_a_suggestion_writes_it_and_vouches_for_it(self):
        self._record("job_title", "Procurement Lead", "crm.activity-text")
        suggestion = Suggestion.objects.get(tenant=self.tenant)
        ledger.accept_suggestion(suggestion, decided_by="Brian")
        self.contact.refresh_from_db()
        suggestion.refresh_from_db()
        self.assertEqual(self.contact.job_title, "Procurement Lead")
        self.assertEqual(suggestion.status, Suggestion.Status.ACCEPTED)
        self.assertTrue(suggestion.evidence.applied)

    def test_evidence_cannot_reach_another_tenants_record(self):
        other = make_tenant("otherco")
        out = ledger.record_observation(
            other, Subject.CONTACT, self.contact.pk, "phone", "+254711000111",
            "crm.signature-block",
        )
        self.contact.refresh_from_db()
        self.assertEqual(out["outcome"], "discarded")
        self.assertEqual(self.contact.phone, "")


class AgentQueueTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(tenant=self.tenant, first_name="Q")

    def _schedule(self, **kw):
        defaults = dict(
            tenant=self.tenant, kind=AgentTask.Kind.RESEARCH_CONTACT,
            subject_type=Subject.CONTACT, subject_id=self.contact.pk,
            reason="test", due_in_days=0,
        )
        defaults.update(kw)
        return agent_queue.schedule(**defaults)

    def test_claiming_leases_the_task_to_one_worker(self):
        task = self._schedule()
        claimed = agent_queue.claim_due(tenant=self.tenant, limit=5)
        self.assertEqual([t.pk for t in claimed], [task.pk])
        self.assertEqual(claimed[0].status, AgentTask.Status.RUNNING)
        self.assertTrue(claimed[0].lease_owner)
        # A second dispatcher finds nothing while the lease holds.
        self.assertEqual(agent_queue.claim_due(tenant=self.tenant, limit=5), [])

    def test_an_expired_lease_is_reclaimed(self):
        task = self._schedule()
        agent_queue.claim_due(tenant=self.tenant, limit=1)
        AgentTask.objects.filter(pk=task.pk).update(
            lease_expires_at=timezone.now() - timedelta(minutes=1)
        )
        reclaimed = agent_queue.claim_due(tenant=self.tenant, limit=1)
        self.assertEqual([t.pk for t in reclaimed], [task.pk])
        self.assertEqual(reclaimed[0].attempts, 2)

    def test_future_work_is_not_claimed_early(self):
        self._schedule(due_in_days=5)
        self.assertEqual(agent_queue.claim_due(tenant=self.tenant, limit=5), [])

    def test_repeat_requests_collapse_into_one_pending_task(self):
        first = self._schedule(reason="first")
        second = self._schedule(reason="second")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AgentTask.objects.filter(tenant=self.tenant).count(), 1)
        second.refresh_from_db()
        self.assertEqual(second.reason, "second")

    def test_failures_back_off_then_give_up_loudly(self):
        task = self._schedule()
        for _ in range(task.max_attempts):
            agent_queue.claim_due(tenant=self.tenant, limit=1)
            task.refresh_from_db()
            agent_queue.fail(task, "boom")
            task.refresh_from_db()
            AgentTask.objects.filter(pk=task.pk).update(due_at=timezone.now())
        task.refresh_from_db()
        self.assertEqual(task.status, AgentTask.Status.FAILED)
        self.assertIn("boom", task.last_error)

    def test_the_queue_is_tenant_scoped(self):
        other = make_tenant("otherco")
        self._schedule()
        self.assertEqual(agent_queue.claim_due(tenant=other, limit=5), [])


class AgentRunTests(TestCase):
    """The deterministic planner, end to end — no API key required."""

    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="John", last_name="Kamau",
            email="john@acme.co.ke",
        )
        Activity.objects.create(
            tenant=self.tenant, contact=self.contact, type=Activity.Type.EMAIL,
            subject="Re: quote",
            notes=(
                "Thanks, that works for us.\n\n"
                "Regards,\n"
                "John Kamau\n"
                "Procurement Manager\n"
                "+254 722 000 002\n"
            ),
        )

    def test_a_run_leaves_a_brief_and_a_trail(self):
        run = agent_runner.run_now(
            self.tenant, AgentTask.Kind.RESEARCH_CONTACT,
            Subject.CONTACT, self.contact.pk, reason="test",
        )
        self.assertEqual(run.status, AgentRun.Status.DONE)
        self.assertTrue(run.brief)
        self.assertTrue(run.steps.exists())
        self.assertEqual(run.planner, "playbook")

    def test_the_run_reads_the_signature_block_and_records_it(self):
        agent_runner.run_now(
            self.tenant, AgentTask.Kind.RESEARCH_CONTACT,
            Subject.CONTACT, self.contact.pk,
        )
        self.contact.refresh_from_db()
        # A signature block clears the write bar, so both fields land directly.
        self.assertEqual(self.contact.phone, "+254722000002")
        self.assertEqual(self.contact.job_title, "Procurement Manager")
        self.assertTrue(
            Evidence.objects.filter(
                tenant=self.tenant, source="crm.signature-block", applied=True
            ).exists()
        )

    def test_the_agent_schedules_its_own_next_look(self):
        agent_runner.run_now(
            self.tenant, AgentTask.Kind.RESEARCH_CONTACT,
            Subject.CONTACT, self.contact.pk,
        )
        self.assertTrue(
            AgentTask.objects.filter(
                tenant=self.tenant, scheduled_by_agent=True,
                status=AgentTask.Status.QUEUED,
            ).exists()
        )

    def test_a_failing_tool_is_recorded_rather_than_swallowed(self):
        ctx = agent_tools.ToolContext(
            tenant=self.tenant,
            run=AgentRun.objects.create(tenant=self.tenant, planner="playbook"),
        )
        result = agent_tools.call(ctx, "read_crm_history",
                                  subject_type="contact", subject_id=999999)
        self.assertIn("error", result)
        step = ctx.run.steps.first()
        self.assertFalse(step.ok)

    def test_an_unknown_tool_does_not_crash_the_run(self):
        ctx = agent_tools.ToolContext(
            tenant=self.tenant,
            run=AgentRun.objects.create(tenant=self.tenant, planner="playbook"),
        )
        result = agent_tools.call(ctx, "definitely_not_a_tool")
        self.assertIn("error", result)

    def test_sweeping_queues_work_without_anyone_asking(self):
        Opportunity.objects.create(
            tenant=self.tenant, name="Deal", contact=self.contact,
            stage="prospecting", amount=100000,
        )
        queued = agent_runner.sweep(self.tenant)
        self.assertTrue(queued)
        self.assertTrue(
            AgentTask.objects.filter(
                tenant=self.tenant, kind=AgentTask.Kind.REVIEW_DEAL
            ).exists()
        )


class TrustScoreTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()

    def _contact(self, age_days=0, **kw):
        defaults = dict(
            tenant=self.tenant, first_name="Grace", last_name="Wanjiru",
            email="grace@acme.co.ke", phone="+254711000003",
            job_title="Director", territory="kiambu",
        )
        defaults.update(kw)
        contact = Contact.objects.create(**defaults)
        if age_days:
            Contact.objects.filter(pk=contact.pk).update(
                created_at=timezone.now() - timedelta(days=age_days)
            )
            contact.refresh_from_db()
        return contact

    def test_a_fresh_hand_typed_record_is_unverified_not_verified(self):
        report = trust.trust_report(self._contact(), Subject.CONTACT)
        states = {f["field"]: f["state"] for f in report["fields"]}
        self.assertEqual(states["phone"], "unverified")
        self.assertGreater(report["score"], 40)

    def test_confidence_decays_with_age(self):
        fresh = trust.trust_report(self._contact(age_days=0), Subject.CONTACT)["score"]
        old = trust.trust_report(self._contact(age_days=900), Subject.CONTACT)["score"]
        self.assertLess(old, fresh)

    def test_confirming_a_field_restores_it(self):
        contact = self._contact(age_days=900)
        before = trust.trust_report(contact, Subject.CONTACT)
        trust.confirm_field(
            self.tenant, Subject.CONTACT, contact.pk, "phone", contact.phone,
            "crm.payment-confirmation", detail="payment ABC123",
        )
        after = trust.trust_report(contact, Subject.CONTACT)
        self.assertGreater(after["score"], before["score"])
        phone = next(f for f in after["fields"] if f["field"] == "phone")
        self.assertEqual(phone["state"], "verified")

    def test_a_blank_field_scores_zero_and_is_flagged(self):
        contact = self._contact(phone="")
        report = trust.trust_report(contact, Subject.CONTACT)
        phone = next(f for f in report["fields"] if f["field"] == "phone")
        self.assertEqual(phone["state"], "missing")
        self.assertEqual(phone["confidence"], 0)
        self.assertIn("phone", [f["field"] for f in report["problems"]])

    def test_the_radar_surfaces_the_worst_records_first(self):
        self._contact(age_days=0)
        rotten = self._contact(age_days=2000, email="", phone="", job_title="")
        radar = trust.decay_radar(self.tenant, limit=10, threshold=100)
        self.assertEqual(radar[0]["object"].pk, rotten.pk)

    def test_the_radar_hands_specific_fields_to_the_agent(self):
        self._contact(age_days=2000, email="", phone="", job_title="")
        queued = trust.queue_reverification(self.tenant, limit=5, threshold=100)
        self.assertTrue(queued)
        task = queued[0]
        self.assertEqual(task.kind, AgentTask.Kind.VERIFY_FIELD)
        self.assertTrue(task.payload["fields"])
        self.assertIn("Trust score", task.reason)


class MpesaReconciliationTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="John", last_name="Kamau",
            phone="0722000002", email="john@acme.co.ke",
        )
        self.deal = Opportunity.objects.create(
            tenant=self.tenant, name="Loyalty module", contact=self.contact,
            stage="proposal", amount=90000,
        )

    SMS = (
        "TGH4X8K9LM Confirmed. Ksh90,000.00 received from JOHN KAMAU 0722000002 "
        "on 9/8/26 at 3:45 PM. New Account balance is Ksh10,000.00"
    )

    def test_phone_numbers_normalise_to_one_form(self):
        for raw in ("+254722000002", "254722000002", "0722000002", "722000002"):
            self.assertEqual(payments.normalise_phone(raw), "722000002")

    def test_the_confirmation_parses(self):
        parsed = payments.parse_mpesa_text(self.SMS)
        self.assertEqual(parsed["external_ref"], "TGH4X8K9LM")
        self.assertEqual(parsed["amount"], Decimal("90000.00"))
        self.assertEqual(parsed["payer_name"], "John Kamau")
        self.assertEqual(parsed["phone"], "722000002")
        self.assertIsNotNone(parsed["paid_at"])

    def test_an_unambiguous_payment_closes_the_deal(self):
        payment = payments.record_payment(self.tenant, text=self.SMS)
        self.deal.refresh_from_db()
        self.contact.refresh_from_db()
        won = next(s.key for s in services.tenant_stages(self.tenant) if s.is_won)
        self.assertEqual(payment.status, PaymentEvent.Status.MATCHED)
        self.assertEqual(payment.opportunity, self.deal)
        self.assertEqual(self.deal.stage, won)
        self.assertEqual(self.contact.lifecycle, Contact.Lifecycle.CUSTOMER)
        self.assertTrue(
            Activity.objects.filter(
                tenant=self.tenant, subject__startswith="Payment received"
            ).exists()
        )

    def test_the_paying_number_becomes_verified_evidence(self):
        payments.record_payment(self.tenant, text=self.SMS)
        self.assertTrue(
            Evidence.objects.filter(
                tenant=self.tenant, field="phone",
                source="crm.payment-confirmation", applied=True,
            ).exists()
        )

    def test_replaying_the_same_confirmation_cannot_double_count(self):
        first = payments.record_payment(self.tenant, text=self.SMS)
        second = payments.record_payment(self.tenant, text=self.SMS)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentEvent.objects.filter(tenant=self.tenant).count(), 1)

    def test_a_part_payment_does_not_close_the_deal(self):
        sms = self.SMS.replace("Ksh90,000.00", "Ksh20,000.00")
        payments.record_payment(self.tenant, text=sms)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, "proposal")

    def test_two_equally_plausible_deals_go_to_a_human(self):
        Opportunity.objects.create(
            tenant=self.tenant, name="Second deal", contact=self.contact,
            stage="proposal", amount=90000,
        )
        payment = payments.record_payment(self.tenant, text=self.SMS)
        self.assertEqual(payment.status, PaymentEvent.Status.NEEDS_REVIEW)
        self.assertIn("identically", payment.match_reason)
        self.assertTrue(
            AgentTask.objects.filter(
                tenant=self.tenant, kind=AgentTask.Kind.RECONCILE_PAYMENT
            ).exists()
        )

    def test_an_unknown_payer_is_left_unmatched_not_guessed(self):
        sms = self.SMS.replace("JOHN KAMAU 0722000002", "ANONYMOUS PERSON 0799999999")
        payment = payments.record_payment(self.tenant, text=sms)
        self.assertEqual(payment.status, PaymentEvent.Status.UNMATCHED)
        self.assertIsNone(payment.contact)

    def test_a_daraja_callback_reconciles_the_same_way(self):
        payload = {
            "TransID": "TGH4X8K9ZZ", "TransAmount": "90000",
            "MSISDN": "254722000002", "FirstName": "JOHN", "LastName": "KAMAU",
            "TransTime": "20260809154500", "BillRefNumber": str(self.deal.pk),
        }
        payment = payments.record_payment(self.tenant, payload=payload)
        self.assertEqual(payment.status, PaymentEvent.Status.MATCHED)
        self.assertEqual(payment.opportunity, self.deal)

    def test_the_webhook_is_idempotent_and_tenant_scoped(self):
        c = client_for()
        payload = {
            "TransID": "TGH4X8K9YY", "TransAmount": "90000",
            "MSISDN": "254722000002", "FirstName": "JOHN", "LastName": "KAMAU",
            "TransTime": "20260809154500",
        }
        for _ in range(2):
            resp = c.post(
                reverse("crm:mpesa_confirmation"), data=payload,
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["ResultCode"], 0)
        self.assertEqual(PaymentEvent.objects.filter(tenant=self.tenant).count(), 1)


class DealRoomTests(TestCase):
    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="Peter", last_name="Ouma",
            email="peter@acme.co.ke",
        )
        self.deal = Opportunity.objects.create(
            tenant=self.tenant, name="Rollout", contact=self.contact,
            stage="proposal", amount=480000,
        )

    def test_a_room_is_prefilled_from_the_deal_and_only_made_once(self):
        room = dealroom.ensure_room(self.deal)
        self.assertEqual(room.total, 480000)
        self.assertTrue(room.line_items)
        self.assertEqual(dealroom.ensure_room(self.deal).pk, room.pk)
        self.assertEqual(DealRoom.objects.filter(opportunity=self.deal).count(), 1)

    def test_the_public_page_works_without_a_login(self):
        room = dealroom.ensure_room(self.deal)
        resp = Client(SERVER_NAME="127.0.0.1").get(room.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Rollout")

    def test_a_closed_room_stops_working(self):
        room = dealroom.ensure_room(self.deal)
        room.active = False
        room.save(update_fields=["active"])
        resp = Client(SERVER_NAME="127.0.0.1").get(room.get_absolute_url())
        self.assertEqual(resp.status_code, 404)

    def test_opens_are_counted_and_visitors_deduplicated(self):
        room = dealroom.ensure_room(self.deal)
        c = Client(SERVER_NAME="127.0.0.1", HTTP_USER_AGENT="TestBrowser/1.0")
        for _ in range(3):
            c.get(room.get_absolute_url())
        stats = dealroom.engagement(room)
        self.assertEqual(stats["views"], 3)
        self.assertEqual(stats["visitors"], 1)

    def test_repeated_opens_with_no_reply_raise_a_signal(self):
        room = dealroom.ensure_room(self.deal)
        DealRoom.objects.filter(pk=room.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        room.refresh_from_db()
        c = Client(SERVER_NAME="127.0.0.1", HTTP_USER_AGENT="TestBrowser/1.0")
        for _ in range(3):
            c.get(room.get_absolute_url())
        self.assertTrue(
            AgentTask.objects.filter(
                tenant=self.tenant, kind=AgentTask.Kind.DEAL_ROOM_SIGNAL
            ).exists()
        )

    def test_accepting_logs_the_commitment_and_the_next_step(self):
        room = dealroom.ensure_room(self.deal)
        resp = Client(SERVER_NAME="127.0.0.1").post(
            reverse("crm:deal_room_accept", args=[room.token]),
            {"name": "Peter Ouma", "note": "Please proceed."},
        )
        room.refresh_from_db()
        self.deal.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(room.accepted_at)
        self.assertTrue(
            Activity.objects.filter(
                tenant=self.tenant, subject__startswith="Deal room accepted"
            ).exists()
        )
        self.assertTrue(
            Activity.objects.filter(
                tenant=self.tenant, type=Activity.Type.TASK, done=False,
                subject__startswith="Send payment details",
            ).exists()
        )
        # Accepting is a commitment, not money — the deal must not read as won.
        self.assertEqual(self.deal.stage, "proposal")

    def test_accepting_twice_does_not_duplicate_the_follow_up(self):
        room = dealroom.ensure_room(self.deal)
        dealroom.accept(room, name="Peter Ouma")
        dealroom.accept(room, name="Someone Else")
        room.refresh_from_db()
        self.assertEqual(room.accepted_by_name, "Peter Ouma")
        self.assertEqual(
            Activity.objects.filter(
                tenant=self.tenant, subject__startswith="Deal room accepted"
            ).count(),
            1,
        )


class AgentConsoleViewTests(TestCase):
    """The surfaces a rep actually clicks."""

    def setUp(self):
        self.tenant = make_tenant()
        self.contact = Contact.objects.create(
            tenant=self.tenant, first_name="Asha", last_name="Mwangi",
            email="asha@acme.co.ke",
        )

    def test_the_console_pages_render(self):
        c = client_for()
        for name in ("agent_inbox", "trust_dashboard", "payments_console", "deal_rooms"):
            self.assertEqual(c.get(reverse(f"crm:{name}")).status_code, 200)

    def test_a_rep_can_accept_a_suggestion_from_the_inbox(self):
        ledger.record_observation(
            self.tenant, Subject.CONTACT, self.contact.pk, "job_title",
            "Head of Ops", "crm.activity-text",
        )
        suggestion = Suggestion.objects.get(tenant=self.tenant)
        resp = client_for().post(
            reverse("crm:suggestion_decide", args=[suggestion.pk]),
            {"decision": "accept", "by": "tester"},
        )
        self.contact.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.contact.job_title, "Head of Ops")

    def test_a_rep_can_answer_an_open_question(self):
        question = AgentQuestion.objects.create(
            tenant=self.tenant, subject_type=Subject.CONTACT,
            subject_id=self.contact.pk, question="Confirm the phone?",
        )
        client_for().post(
            reverse("crm:question_answer", args=[question.pk]), {"answer": "Confirmed."}
        )
        question.refresh_from_db()
        self.assertEqual(question.status, AgentQuestion.Status.ANSWERED)

    def test_ask_the_agent_runs_immediately(self):
        client_for().post(reverse("crm:agent_run_now"), {
            "subject_type": "contact", "subject_id": self.contact.pk,
        })
        self.assertTrue(AgentRun.objects.filter(tenant=self.tenant).exists())

    def test_one_tenant_cannot_decide_anothers_suggestion(self):
        other = make_tenant("otherco")
        ledger.record_observation(
            self.tenant, Subject.CONTACT, self.contact.pk, "job_title",
            "Head of Ops", "crm.activity-text",
        )
        suggestion = Suggestion.objects.get(tenant=self.tenant)
        resp = client_for("otherco").post(
            reverse("crm:suggestion_decide", args=[suggestion.pk]), {"decision": "accept"}
        )
        suggestion.refresh_from_db()
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(suggestion.status, Suggestion.Status.PENDING)
        self.assertTrue(other.pk)


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
