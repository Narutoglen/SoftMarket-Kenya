"""JSON API for the white-label CRM core.

Style mirrors ``marketplace.api``: DRF ``APIView`` + ``AllowAny`` for the
public intake endpoint (no session/CSRF), and simple list/detail views for the
internal front office. All data is scoped to a Tenant resolved from the
``X-CRM-Instance`` header (defaults to ``softmarket``).

Endpoints (namespaced under /api/crm/):
  POST /api/crm/leads/            public web-form intake -> auto BANT + assign
  GET  /api/crm/leads/            list leads (optional ?rating=hot)
  GET  /api/crm/contacts/         list contacts (360 hub)
  GET  /api/crm/contacts/<id>/    contact + activities + opportunities
  POST /api/crm/contacts/<id>/activities/   log an activity
  GET  /api/crm/accounts/         list accounts
  GET  /api/crm/opportunities/    list opportunities
  GET  /api/crm/pipeline/         forecast summary by stage
  POST /api/crm/leads/<id>/convert/   promote a lead to a contact
  POST /api/crm/contacts/merge/   dedupe/merge by email or phone
"""

from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    Account,
    Activity,
    Contact,
    Lead,
    Opportunity,
    Tenant,
)


def resolve_tenant(request):
    """Resolve the active CRM instance from header or default 'softmarket'."""
    slug = request.headers.get("X-CRM-Instance") or request.GET.get("instance") or "softmarket"
    return Tenant.objects.filter(slug=slug, active=True).first()


class LeadSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Lead
        fields = (
            "id", "full_name", "first_name", "last_name", "email", "phone",
            "company", "territory", "source", "message",
            "bant_budget", "bant_authority", "bant_need", "bant_timeline",
            "rating", "owner", "auto_responded", "created_at",
        )
        read_only_fields = ("rating", "owner", "auto_responded", "created_at")


class ContactSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Contact
        fields = (
            "id", "full_name", "first_name", "last_name", "email", "phone",
            "date_of_birth", "personal_notes", "account", "lifecycle",
            "territory", "created_at",
        )


class ContactDetailSerializer(ContactSerializer):
    activities = serializers.SerializerMethodField()
    opportunities = serializers.SerializerMethodField()

    class Meta(ContactSerializer.Meta):
        fields = ContactSerializer.Meta.fields + ("activities", "opportunities")

    def get_activities(self, obj):
        return [
            {"id": a.id, "type": a.type, "subject": a.subject,
             "notes": a.notes, "due_at": a.due_at, "done": a.done,
             "created_at": a.created_at}
            for a in obj.activities.all()[:50]
        ]

    def get_opportunities(self, obj):
        return [
            {"id": o.id, "name": o.name, "stage": o.stage,
             "amount": o.amount, "probability": o.probability}
            for o in obj.opportunities.all()[:50]
        ]


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ("id", "name", "industry", "website", "phone", "created_at")


class OpportunitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Opportunity
        fields = (
            "id", "name", "contact", "account", "stage", "amount",
            "probability", "expected_close_date", "owner", "created_at",
        )


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ("id", "contact", "type", "subject", "notes", "due_at", "done")


# ---------------------------------------------------------------------------
# Public intake: web-form -> lead (automation entry point)
# ---------------------------------------------------------------------------
class LeadIntakeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # JSON API — no session/CSRF

    def get(self, request):
        # GET /api/crm/leads/ lists leads (documented contract + REST
        # convention). The list logic lives in LeadListView; reuse it so the
        # two routes stay in sync. (The /api/crm/leads/list/ alias is kept for
        # backward compatibility.)
        return LeadListView().get(request)

    def post(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        data = request.data
        lead = Lead.objects.create(
            tenant=tenant,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            company=data.get("company", ""),
            territory=data.get("territory", ""),
            source=data.get("source", Lead.Source.WEB_FORM),
            message=data.get("message", ""),
            bant_budget=int(data.get("bant_budget", 0) or 0),
            bant_authority=int(data.get("bant_authority", 0) or 0),
            bant_need=int(data.get("bant_need", 0) or 0),
            bant_timeline=int(data.get("bant_timeline", 0) or 0),
        )
        # Automation: score BANT + auto-assign owner + auto-responder email.
        services.intake_lead(lead)
        return Response(
            {
                "id": lead.id,
                "rating": lead.rating,
                "owner": lead.owner,
                "message": "Thanks! A specialist will reach out within 24 hours.",
            },
            status=201,
        )


class LeadListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        qs = Lead.objects.filter(tenant=tenant)
        rating = request.GET.get("rating")
        if rating:
            qs = qs.filter(rating=rating)
        # Pagination: high-volume safety (no full-table dumps to the client).
        try:
            limit = min(int(request.GET.get("limit", 100)), 500)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 100, 0
        total = qs.count()
        page = qs[offset:offset + limit]
        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
            "results": LeadSerializer(page, many=True).data,
        })


class ContactListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        qs = Contact.objects.filter(tenant=tenant)
        # Pagination: high-volume safety (no full-table dumps to the client).
        try:
            limit = min(int(request.GET.get("limit", 100)), 500)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except (TypeError, ValueError):
            limit, offset = 100, 0
        total = qs.count()
        page = qs[offset:offset + limit]
        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
            "results": ContactSerializer(page, many=True).data,
        })


class ContactDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        contact = Contact.objects.filter(tenant=tenant, pk=pk).first()
        if not contact:
            return Response({"detail": "Not found."}, status=404)
        return Response(ContactDetailSerializer(contact).data)


class ActivityCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, pk):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        contact = Contact.objects.filter(tenant=tenant, pk=pk).first()
        if not contact:
            return Response({"detail": "Contact not found."}, status=404)
        data = request.data
        activity = Activity.objects.create(
            tenant=tenant,
            contact=contact,
            type=data.get("type", Activity.Type.NOTE),
            subject=data.get("subject", ""),
            notes=data.get("notes", ""),
            due_at=data.get("due_at"),
            done=bool(data.get("done", False)),
        )
        return Response(ActivitySerializer(activity).data, status=201)


class AccountListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        return Response(AccountSerializer(
            Account.objects.filter(tenant=tenant), many=True).data)


class OpportunityListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        return Response(OpportunitySerializer(
            Opportunity.objects.filter(tenant=tenant), many=True).data)


class PipelineView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        return Response(services.pipeline_summary(tenant))


class LeadConvertView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, pk):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        lead = Lead.objects.filter(tenant=tenant, pk=pk).first()
        if not lead:
            return Response({"detail": "Lead not found."}, status=404)
        create_account = bool(request.data.get("create_account", False))
        contact = services.convert_lead_to_contact(lead, create_account=create_account)
        return Response(
            {"contact_id": contact.id, "message": "Lead converted to contact."},
            status=201,
        )


class ContactMergeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        email = request.data.get("email")
        phone = request.data.get("phone")
        if not email and not phone:
            return Response({"detail": "Provide email or phone to merge."}, status=400)
        dups = list(services.find_duplicate_contacts(tenant, email=email, phone=phone))
        if len(dups) < 2:
            return Response({"merged": 0, "message": "No duplicates found."})
        primary = dups[0]
        merged = services.merge_contacts(primary, dups[1:])
        return Response({"merged": merged, "primary_id": primary.id})
