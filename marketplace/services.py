import base64
import csv
import json
import zipfile
from datetime import datetime
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Sum
from django.utils import timezone

from .models import (
    Assignment,
    DeveloperApplication,
    DeveloperProfile,
    NotificationLog,
    Payment,
    ProjectRequest,
    ServiceCategory,
)


DEFAULT_SERVICES = [
    ("Business website", "business-website", 20_000, 80_000, 2_000, False),
    ("Ecommerce website", "ecommerce-website", 50_000, 500_000, 5_000, False),
    ("Web app", "web-app", 100_000, 600_000, 5_000, False),
    ("Android app", "android-app", 80_000, 500_000, 10_000, False),
    ("Cross-platform app", "cross-platform-app", 150_000, 800_000, 10_000, False),
    ("Business system", "business-system", 150_000, 1_000_000, 10_000, False),
    ("Maintenance/support", "maintenance-support", 5_000, 30_000, 2_000, True),
]


def seed_default_services():
    for name, slug, min_price, max_price, deposit, monthly in DEFAULT_SERVICES:
        ServiceCategory.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": f"{name} service package",
                "min_price": min_price,
                "max_price": max_price,
                "deposit_amount": deposit,
                "monthly": monthly,
            },
        )


def normalize_service_label(label):
    return (label or "").strip().lower().replace("_", " ").replace("-", " ")


def get_service_for_label(label):
    normalized = normalize_service_label(label)
    aliases = {
        "business website": "business-website",
        "business websites": "business-website",
        "ecommerce website": "ecommerce-website",
        "ecommerce websites": "ecommerce-website",
        "web app": "web-app",
        "web apps": "web-app",
        "android app": "android-app",
        "android apps": "android-app",
        "cross platform app": "cross-platform-app",
        "cross platform apps": "cross-platform-app",
        "cross-platform app": "cross-platform-app",
        "cross-platform apps": "cross-platform-app",
        "business system": "business-system",
        "business systems": "business-system",
        "maintenance/support": "maintenance-support",
        "maintenance": "maintenance-support",
        "support": "maintenance-support",
    }
    slug = aliases.get(normalized)
    if slug:
        return ServiceCategory.objects.filter(slug=slug, active=True).first()
    return ServiceCategory.objects.filter(name__iexact=label, active=True).first()


def generate_quote(project):
    service = project.service or get_service_for_label(project.service_label)
    if not service:
        return project

    budget_text = project.budget or ""
    multipliers = {
        "Within 2-4 weeks": 1.12,
        "Within 1-2 months": 1.0,
        "Within 3 months": 0.95,
        "Still exploring": 0.9,
    }
    multiplier = multipliers.get(project.timeline, 1.0)
    details_words = len((project.details or "").split())
    complexity = 1.15 if details_words > 80 else 1.0

    estimated_min = int(service.min_price * multiplier * complexity)
    estimated_max = int((service.max_price or service.min_price * 2) * multiplier * complexity)

    if "600,000+" in budget_text and estimated_max < 600_000:
        estimated_max = 600_000

    project.service = service
    project.estimated_min = estimated_min
    project.estimated_max = estimated_max
    project.deposit_amount = service.deposit_amount
    project.status = ProjectRequest.Status.QUOTED
    project.save(
        update_fields=[
            "service",
            "estimated_min",
            "estimated_max",
            "deposit_amount",
            "status",
            "updated_at",
        ]
    )
    return project


def assign_best_developers(project, limit=3):
    service = project.service or get_service_for_label(project.service_label)
    if not service:
        return []

    developers = DeveloperProfile.objects.filter(
        status=DeveloperProfile.Status.VETTED,
        service_categories=service,
    ).distinct()

    assignments = []
    for developer in developers:
        score = (developer.availability_score * 10) + (developer.quality_score * 10)
        if normalize_service_label(service.name).split()[0] in normalize_service_label(developer.stack):
            score += 10
        assignment, _ = Assignment.objects.update_or_create(
            project=project,
            developer=developer,
            defaults={
                "score": score,
                "reason": f"Matched on {service.name}, availability, and quality score.",
            },
        )
        assignments.append(assignment)

    assignments.sort(key=lambda item: item.score, reverse=True)
    selected = assignments[:limit]
    if selected and project.status in {ProjectRequest.Status.NEW, ProjectRequest.Status.QUOTED}:
        project.status = ProjectRequest.Status.MATCHED
        project.save(update_fields=["status", "updated_at"])
    return selected


def create_developer_from_application(application: DeveloperApplication):
    if application.converted_profile:
        return application.converted_profile
    profile = DeveloperProfile.objects.create(
        name=application.name,
        stack=application.stack,
        portfolio_url=application.portfolio_url,
        status=DeveloperProfile.Status.APPLIED,
    )
    application.converted_profile = profile
    application.save(update_fields=["converted_profile", "updated_at"])
    return profile


def notify_admins_for_project(project):
    subject = f"New SoftMarket project brief: {project.service_label}"
    message = (
        f"Client: {project.name}\n"
        f"Phone: {project.phone}\n"
        f"Email: {project.email}\n"
        f"Service: {project.service_label}\n"
        f"Budget: {project.budget}\n"
        f"Timeline: {project.timeline}\n"
        f"Quote: KSh {project.estimated_min or '-'} - {project.estimated_max or '-'}\n\n"
        f"{project.details}"
    )
    recipients = settings.ADMIN_NOTIFICATION_EMAILS
    if recipients:
        success = send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
        NotificationLog.objects.create(
            channel=NotificationLog.Channel.EMAIL,
            recipient=", ".join(recipients),
            subject=subject,
            message=message,
            success=bool(success),
            project=project,
        )
    send_sms_notification(project.phone, f"SoftMarket Kenya received your {project.service_label} brief.")


def notify_admins_for_developer(application):
    subject = f"New developer application: {application.name}"
    message = f"Name: {application.name}\nStack: {application.stack}\nPortfolio: {application.portfolio_url}"
    recipients = settings.ADMIN_NOTIFICATION_EMAILS
    if recipients:
        success = send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
        NotificationLog.objects.create(
            channel=NotificationLog.Channel.EMAIL,
            recipient=", ".join(recipients),
            subject=subject,
            message=message,
            success=bool(success),
        )


def send_sms_notification(recipient, message):
    if not settings.SOFTMARKET_SMS_WEBHOOK_URL:
        NotificationLog.objects.create(
            channel=NotificationLog.Channel.SMS,
            recipient=recipient,
            message=message,
            success=False,
            provider_response="SMS webhook not configured; message logged only.",
        )
        return False

    headers = {"Content-Type": "application/json"}
    if settings.SOFTMARKET_SMS_WEBHOOK_TOKEN:
        headers["Authorization"] = f"Bearer {settings.SOFTMARKET_SMS_WEBHOOK_TOKEN}"

    try:
        response = requests.post(
            settings.SOFTMARKET_SMS_WEBHOOK_URL,
            headers=headers,
            json={"to": recipient, "message": message},
            timeout=12,
        )
        success = response.ok
        provider_response = response.text[:1000]
    except requests.RequestException as exc:
        success = False
        provider_response = str(exc)

    NotificationLog.objects.create(
        channel=NotificationLog.Channel.SMS,
        recipient=recipient,
        message=message,
        success=success,
        provider_response=provider_response,
    )
    return success


class MpesaClient:
    def __init__(self):
        base = "https://sandbox.safaricom.co.ke"
        if settings.MPESA_ENVIRONMENT == "production":
            base = "https://api.safaricom.co.ke"
        self.base_url = base

    def configured(self):
        return all(
            [
                settings.MPESA_CONSUMER_KEY,
                settings.MPESA_CONSUMER_SECRET,
                settings.MPESA_BUSINESS_SHORTCODE,
                settings.MPESA_PASSKEY,
                settings.MPESA_CALLBACK_URL,
            ]
        )

    def access_token(self):
        response = requests.get(
            f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials",
            auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def initiate_stk_push(self, payment):
        if not self.configured():
            payment.result_description = "M-Pesa credentials not configured."
            payment.save(update_fields=["result_description", "updated_at"])
            return {"configured": False, "message": payment.result_description}

        timestamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
        password_raw = f"{settings.MPESA_BUSINESS_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        password = base64.b64encode(password_raw.encode()).decode()
        phone = normalize_phone(payment.phone)
        payload = {
            "BusinessShortCode": settings.MPESA_BUSINESS_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": settings.MPESA_TRANSACTION_TYPE,
            "Amount": payment.amount,
            "PartyA": phone,
            "PartyB": settings.MPESA_BUSINESS_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": settings.MPESA_CALLBACK_URL,
            "AccountReference": f"SMK-{payment.project_id}",
            "TransactionDesc": "SoftMarket booking deposit",
        }
        response = requests.post(
            f"{self.base_url}/mpesa/stkpush/v1/processrequest",
            headers={"Authorization": f"Bearer {self.access_token()}"},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        payment.merchant_request_id = data.get("MerchantRequestID", "")
        payment.checkout_request_id = data.get("CheckoutRequestID", "")
        payment.status = Payment.Status.STK_SENT
        payment.result_description = data.get("ResponseDescription", "")
        payment.save()
        return data


def normalize_phone(phone):
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0"):
        return f"254{digits[1:]}"
    if digits.startswith("7") and len(digits) == 9:
        return f"254{digits}"
    return digits


def handle_mpesa_callback(payload):
    body = payload.get("Body", {})
    stk = body.get("stkCallback", {})
    checkout_id = stk.get("CheckoutRequestID", "")
    payment = Payment.objects.filter(checkout_request_id=checkout_id).first()
    if not payment:
        return None

    result_code = str(stk.get("ResultCode", ""))
    payment.result_code = result_code
    payment.result_description = stk.get("ResultDesc", "")
    payment.callback_payload = payload

    metadata = stk.get("CallbackMetadata", {}).get("Item", [])
    values = {item.get("Name"): item.get("Value") for item in metadata}
    if result_code == "0":
        payment.status = Payment.Status.PAID
        payment.mpesa_receipt = values.get("MpesaReceiptNumber", "")
        payment.project.status = ProjectRequest.Status.DEPOSIT_PAID
        payment.project.save(update_fields=["status", "updated_at"])
    else:
        payment.status = Payment.Status.FAILED
    payment.save()
    return payment


def create_deposit_payment(project):
    amount = project.deposit_amount or 0
    return Payment.objects.create(project=project, amount=amount, phone=project.phone)


def analytics_summary():
    total_projects = ProjectRequest.objects.count()
    total_developers = DeveloperProfile.objects.count()
    paid_deposits = Payment.objects.filter(status=Payment.Status.PAID).aggregate(
        count=Count("id"), total=Sum("amount")
    )
    popular_services = list(
        ProjectRequest.objects.values("service_label")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )
    campaign_sources = list(
        ProjectRequest.objects.values("utm_source")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )
    return {
        "total_projects": total_projects,
        "total_developers": total_developers,
        "paid_deposit_count": paid_deposits["count"] or 0,
        "paid_deposit_total": paid_deposits["total"] or 0,
        "popular_services": popular_services,
        "campaign_sources": campaign_sources,
    }


def project_requests_csv():
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at",
            "name",
            "phone",
            "email",
            "service",
            "budget",
            "timeline",
            "estimated_min",
            "estimated_max",
            "deposit_amount",
            "status",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "details",
        ]
    )
    for project in ProjectRequest.objects.all():
        writer.writerow(
            [
                timezone.localtime(project.created_at).isoformat(),
                project.name,
                project.phone,
                project.email,
                project.service_label,
                project.budget,
                project.timeline,
                project.estimated_min,
                project.estimated_max,
                project.deposit_amount,
                project.status,
                project.utm_source,
                project.utm_medium,
                project.utm_campaign,
                project.details,
            ]
        )
    return buffer.getvalue()


def project_requests_xlsx():
    headers = [
        "created_at",
        "name",
        "phone",
        "email",
        "service",
        "budget",
        "timeline",
        "estimated_min",
        "estimated_max",
        "deposit_amount",
        "status",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "details",
    ]
    rows = [headers]
    for project in ProjectRequest.objects.all():
        rows.append(
            [
                timezone.localtime(project.created_at).isoformat(),
                project.name,
                project.phone,
                project.email,
                project.service_label,
                project.budget,
                project.timeline,
                project.estimated_min or "",
                project.estimated_max or "",
                project.deposit_amount or "",
                project.status,
                project.utm_source,
                project.utm_medium,
                project.utm_campaign,
                project.details,
            ]
        )

    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            cell_ref = f"{xlsx_column(col_idx)}{row_idx}"
            if isinstance(value, int):
                cells.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
                )
        sheet_rows.append(f"<row r=\"{row_idx}\">{''.join(cells)}</row>")

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        workbook.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        workbook.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Project Requests" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def xlsx_column(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def parsed_json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))
