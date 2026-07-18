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


class PaymentReliabilityTests(TestCase):
    def _project(self):
        return ProjectRequest.objects.create(
            name="Rel Client",
            phone="0712345678",
            email="rel@example.com",
            service_label="Business website",
            budget="KSh 20,000-80,000",
            timeline="Within 1-2 months",
            details="Reliability test.",
            deposit_amount=2_000,
        )

    def test_duplicate_checkout_request_id_rejected(self):
        from django.db import IntegrityError

        project = self._project()
        Payment.objects.create(
            project=project, amount=2_000, phone="0712345678",
            checkout_request_id="ws_CO_DUP",
        )
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                project=project, amount=2_000, phone="0712345678",
                checkout_request_id="ws_CO_DUP",
            )

    def test_blank_checkout_ids_are_not_unique_constrained(self):
        project = self._project()
        Payment.objects.create(project=project, amount=2_000, phone="0712345678")
        other = ProjectRequest.objects.create(
            name="Other", phone="0700000000", email="other@example.com",
            service_label="Web app", budget="-", timeline="-", details="-",
        )
        # Second blank-checkout payment (different project) must be allowed.
        Payment.objects.create(project=other, amount=5_000, phone="0700000000")
        self.assertEqual(Payment.objects.filter(checkout_request_id="").count(), 2)

    def test_create_deposit_payment_reuses_open_payment(self):
        from .services import create_deposit_payment

        project = self._project()
        first = create_deposit_payment(project)
        second = create_deposit_payment(project)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.filter(project=project).count(), 1)
        # Quote changed -> the open payment is refreshed, not duplicated.
        project.deposit_amount = 5_000
        third = create_deposit_payment(project)
        self.assertEqual(third.pk, first.pk)
        self.assertEqual(third.amount, 5_000)

    def test_create_deposit_payment_does_not_reuse_pushed_payment(self):
        from .services import create_deposit_payment

        project = self._project()
        pushed = create_deposit_payment(project)
        pushed.checkout_request_id = "ws_CO_PUSHED"
        pushed.status = Payment.Status.STK_SENT
        pushed.save()
        fresh = create_deposit_payment(project)
        self.assertNotEqual(fresh.pk, pushed.pk)

    def test_stk_network_error_returns_502_and_marks_payment_failed(self):
        from unittest.mock import patch
        import requests as requests_lib

        User.objects.create_superuser("relstaff", "rel@example.com", "password")
        self.client.login(username="relstaff", password="password")
        project = self._project()

        with self.settings(
            MPESA_CONSUMER_KEY="k", MPESA_CONSUMER_SECRET="s",
            MPESA_BUSINESS_SHORTCODE="174379", MPESA_PASSKEY="p",
            MPESA_CALLBACK_URL="https://example.com/cb",
        ), patch(
            "marketplace.services.requests.get",
            side_effect=requests_lib.ConnectionError("boom"),
        ), patch(
            "marketplace.services.requests.post",
            side_effect=requests_lib.ConnectionError("boom"),
        ):
            resp = self.client.post(
                reverse("marketplace:initiate_mpesa_deposit", args=[project.pk])
            )

        self.assertEqual(resp.status_code, 502)
        payment = Payment.objects.get(project=project)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn("STK push failed", payment.result_description)

    def test_stk_not_configured_returns_json_not_500(self):
        User.objects.create_superuser("relstaff2", "rel2@example.com", "password")
        self.client.login(username="relstaff2", password="password")
        project = self._project()
        resp = self.client.post(
            reverse("marketplace:initiate_mpesa_deposit", args=[project.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["result"]["configured"])
