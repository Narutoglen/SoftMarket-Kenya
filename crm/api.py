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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Account,
    Activity,
    AgentRun,
    AgentTask,
    Contact,
    Lead,
    Opportunity,
    PaymentEvent,
    Subject,
    Suggestion,
    Tenant,
    TenantMembership,
)
from . import services


def resolve_tenant(request):
    """Resolve the active CRM instance for the front office (HTML + API).

    Priority:
      1. Authenticated user -> their pinned active_tenant (session), validated
         against their actual TenantMembership (never trusts a raw header).
      2. Explicit ?instance=/X-CRM-Instance header -> only for the PUBLIC
         softmarket instance (anonymous browsing / public lead intake).
      3. Default 'softmarket' public tenant.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        slug = request.session.get("active_tenant")
        if slug:
            m = TenantMembership.objects.filter(
                user=user, tenant__slug=slug, tenant__active=True
            ).select_related("tenant").first()
            if m:
                return m.tenant
        # Fall back to the user's first membership.
        m = TenantMembership.objects.filter(
            user=user, tenant__active=True
        ).select_related("tenant").order_by("tenant__name").first()
        if m:
            return m.tenant
        return None  # authenticated but no tenant -> no access

    # Anonymous: header-driven, public only.
    slug = request.headers.get("X-CRM-Instance") or request.GET.get("instance")
    if slug:
        return Tenant.objects.filter(slug=slug, active=True, is_public=True).first()
    return Tenant.objects.filter(slug="softmarket", active=True, is_public=True).first()


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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        contact = Contact.objects.filter(tenant=tenant, pk=pk).first()
        if not contact:
            return Response({"detail": "Not found."}, status=404)
        return Response(ContactDetailSerializer(contact).data)


class ActivityCreateView(APIView):
    permission_classes = [IsAuthenticated]
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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        return Response(AccountSerializer(
            Account.objects.filter(tenant=tenant), many=True).data)


class OpportunityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        return Response(OpportunitySerializer(
            Opportunity.objects.filter(tenant=tenant), many=True).data)


class PipelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        return Response(services.pipeline_summary(tenant))


class LeadConvertView(APIView):
    permission_classes = [IsAuthenticated]
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
    permission_classes = [IsAuthenticated]
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


# ---------------------------------------------------------------------------
# M7 — the agent, the trust layer and payments over JSON
#
# Same contract as the HTML front office, so an external dashboard or a mobile
# app sees exactly what a rep sees, including the reasoning.
# ---------------------------------------------------------------------------
class AgentTaskView(APIView):
    """GET the queue; POST to queue (and optionally run) a task."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        from .agent import queue as agent_queue

        return Response({
            "depth": agent_queue.queue_depth(tenant),
            "upcoming": [
                {
                    "id": t.id, "kind": t.kind, "subject_type": t.subject_type,
                    "subject_id": t.subject_id, "subject": t.subject_label,
                    "reason": t.reason, "due_at": t.due_at,
                    "scheduled_by_agent": t.scheduled_by_agent, "status": t.status,
                }
                for t in agent_queue.upcoming(tenant, limit=50)
            ],
        })

    def post(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        from .agent import queue as agent_queue, runner as agent_runner

        data = request.data
        subject_type = data.get("subject_type", Subject.CONTACT)
        subject_id = int(data.get("subject_id", 0) or 0)
        kind = data.get("kind", AgentTask.Kind.RESEARCH_CONTACT)
        reason = data.get("reason", "Queued over the API.")

        if data.get("run_now"):
            run = agent_runner.run_now(tenant, kind, subject_type, subject_id, reason=reason)
            return Response({
                "run_id": run.id, "status": run.status, "brief": run.brief,
                "steps": [
                    {"tool": s.tool, "summary": s.summary, "ok": s.ok}
                    for s in run.steps.all()
                ],
            }, status=201)

        task = agent_queue.schedule(
            tenant=tenant, kind=kind, subject_type=subject_type,
            subject_id=subject_id, reason=reason,
            due_in_days=int(data.get("due_in_days", 0) or 0),
        )
        return Response({"task_id": task.id, "due_at": task.due_at}, status=201)


class AgentRunListView(APIView):
    """The Agent tab as data: runs, their briefs, and every step taken."""

    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        qs = AgentRun.objects.filter(tenant=tenant).select_related("task")
        subject_type = request.GET.get("subject_type")
        subject_id = request.GET.get("subject_id")
        if subject_type and subject_id:
            qs = qs.filter(task__subject_type=subject_type, task__subject_id=subject_id)
        return Response({
            "results": [
                {
                    "id": run.id, "status": run.status, "planner": run.planner,
                    "model": run.model, "brief": run.brief,
                    "started_at": run.started_at, "finished_at": run.finished_at,
                    "subject": run.task.subject_label if run.task else None,
                    "reason": run.task.reason if run.task else "",
                    "steps": [
                        {
                            "seq": s.seq, "tool": s.tool, "summary": s.summary,
                            "ok": s.ok, "duration_ms": s.duration_ms,
                            "input": s.tool_input, "output": s.tool_output,
                        }
                        for s in run.steps.all()
                    ],
                }
                for run in qs[:25]
            ]
        })


class SuggestionListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        qs = Suggestion.objects.filter(tenant=tenant)
        status_filter = request.GET.get("status", Suggestion.Status.PENDING)
        if status_filter != "all":
            qs = qs.filter(status=status_filter)
        return Response({
            "results": [
                {
                    "id": s.id, "subject_type": s.subject_type, "subject_id": s.subject_id,
                    "subject": s.subject_label, "field": s.field,
                    "current_value": s.current_value, "proposed_value": s.proposed_value,
                    "confidence": s.confidence, "rationale": s.rationale,
                    "status": s.status, "source": s.evidence.source if s.evidence else "",
                }
                for s in qs[:100]
            ]
        })


class SuggestionDecideView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, pk):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        suggestion = Suggestion.objects.filter(tenant=tenant, pk=pk).first()
        if not suggestion:
            return Response({"detail": "Suggestion not found."}, status=404)
        from .agent import evidence as ledger

        decision = request.data.get("decision")
        who = request.data.get("by", "api")
        if decision == "accept":
            ledger.accept_suggestion(suggestion, decided_by=who)
        elif decision == "reject":
            ledger.reject_suggestion(suggestion, decided_by=who)
        else:
            return Response({"detail": "decision must be 'accept' or 'reject'."}, status=400)
        return Response({"id": suggestion.id, "status": suggestion.status})


class TrustView(APIView):
    """Portfolio trust, the decay radar, or one record's field-by-field report."""

    permission_classes = [AllowAny]

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        from . import trust as trust_service
        from .agent import evidence as ledger

        subject_type = request.GET.get("subject_type")
        subject_id = request.GET.get("subject_id")
        if subject_type and subject_id:
            subject = ledger.resolve_subject(tenant, subject_type, int(subject_id))
            if subject is None:
                return Response({"detail": "Not found."}, status=404)
            report = trust_service.trust_report(subject, subject_type)
            return Response({
                "score": report["score"], "band": report["band"],
                "fields": [
                    {
                        "field": f["field"], "label": f["label"], "state": f["state"],
                        "confidence": f["confidence"], "source": f["source"],
                        "verified_at": f["verified_at"], "explanation": f["explanation"],
                    }
                    for f in report["fields"]
                ],
            })

        return Response({
            "portfolio": trust_service.portfolio_trust(tenant),
            "radar": [
                {
                    "subject_type": row["subject_type"], "id": row["object"].pk,
                    "label": row["label"], "score": row["score"], "band": row["band"],
                    "problems": [f["field"] for f in row["problems"]],
                }
                for row in trust_service.decay_radar(tenant, limit=50)
            ],
        })


class PaymentView(APIView):
    """GET the payment ledger; POST a confirmation to reconcile it."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        from . import payments as payments_service

        qs = PaymentEvent.objects.filter(tenant=tenant)
        if request.GET.get("status"):
            qs = qs.filter(status=request.GET["status"])
        return Response({
            "summary": payments_service.payment_summary(tenant),
            "results": [
                {
                    "id": p.id, "ref": p.external_ref, "amount": str(p.amount),
                    "payer_name": p.payer_name, "phone": p.phone, "status": p.status,
                    "paid_at": p.paid_at, "contact_id": p.contact_id,
                    "opportunity_id": p.opportunity_id,
                    "match_confidence": p.match_confidence, "match_reason": p.match_reason,
                }
                for p in qs[:100]
            ],
        })

    def post(self, request):
        tenant = resolve_tenant(request)
        if not tenant:
            return Response({"detail": "Unknown CRM instance."}, status=404)
        from . import payments as payments_service

        text = request.data.get("text", "")
        payload = request.data.get("payload")
        if not text and not payload:
            return Response(
                {"detail": "Send either 'text' (the SMS) or 'payload' (a Daraja body)."},
                status=400,
            )
        payment = payments_service.record_payment(tenant, text=text, payload=payload)
        return Response({
            "id": payment.id, "status": payment.status, "amount": str(payment.amount),
            "contact_id": payment.contact_id, "opportunity_id": payment.opportunity_id,
            "match_confidence": payment.match_confidence,
            "match_reason": payment.match_reason,
        }, status=201)
