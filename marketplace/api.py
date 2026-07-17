"""JSON API layer for the Next.js frontend.

Everything here is ADDITIVE — the existing server-rendered HTML views in
`views.py` keep working untouched, so the legacy site remains a safe fallback.
These endpoints are what the React/Next.js frontend consumes.

Endpoints:
  GET  /api/services/                       active service categories (pricing)
  GET  /api/blog/                           published blog posts (list)
  GET  /api/blog/<slug>/                    published blog post (detail)
  GET  /api/process/                        the "how it works" steps (static copy)
  POST /api/leads/                          submit a project brief
  POST /api/developer-applications/         submit a developer application
"""

from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import DeveloperApplicationForm, ProjectRequestForm
from .models import BlogPost, ServiceCategory
from .services import (
    assign_best_developers,
    generate_quote,
    notify_admins_for_developer,
    notify_admins_for_project,
    seed_default_services,
)

# ---------------------------------------------------------------------------
# Static marketing copy (kept here so the frontend stays a thin consumer).
# `icon` is a semantic key the React frontend maps to an inline SVG.
# ---------------------------------------------------------------------------
PROCESS_STEPS = [
    {
        "step": "01",
        "title": "Submit a brief",
        "description": "Tell us what you need, your budget, and your timeline through the request form.",
        "icon": "document",
    },
    {
        "step": "02",
        "title": "Review scope",
        "description": "We check the request, generate an estimate, and clarify gaps before matching.",
        "icon": "search",
    },
    {
        "step": "03",
        "title": "Match talent",
        "description": "Admins review the project against vetted developer profiles and suggest a fit.",
        "icon": "users",
    },
    {
        "step": "04",
        "title": "Kick off",
        "description": "The client and developer move into WhatsApp-first follow-up and project planning.",
        "icon": "rocket",
    },
]


def _absolute(request, value):
    if not value:
        return None
    if value.startswith("http"):
        return value
    return request.build_absolute_uri(value)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "min_price",
            "max_price",
            "deposit_amount",
            "monthly",
        )


class BlogPostListSerializer(serializers.ModelSerializer):
    author_display = serializers.CharField(read_only=True)
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = (
            "id",
            "slug",
            "title",
            "category",
            "author_display",
            "excerpt",
            "published_at",
            "main_image",
        )

    def get_main_image(self, obj):
        return _absolute(self.context["request"], obj.main_image.url if obj.main_image else None)


class BlogPostDetailSerializer(serializers.ModelSerializer):
    author_display = serializers.CharField(read_only=True)
    main_image = serializers.SerializerMethodField()
    content_image = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = (
            "id",
            "slug",
            "title",
            "category",
            "author_display",
            "excerpt",
            "body",
            "published_at",
            "main_image",
            "content_image",
            "content_image_placement",
        )

    def get_main_image(self, obj):
        return _absolute(self.context["request"], obj.main_image.url if obj.main_image else None)

    def get_content_image(self, obj):
        return _absolute(self.context["request"], obj.content_image.url if obj.content_image else None)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
class ServiceListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = ServiceCategory.objects.filter(active=True)
        return Response(ServiceCategorySerializer(qs, many=True).data)


class BlogListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = BlogPost.objects.filter(
            status=BlogPost.Status.PUBLISHED, published_at__isnull=False
        )
        return Response(
            BlogPostListSerializer(qs, many=True, context={"request": request}).data
        )


class BlogDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        post = BlogPost.objects.filter(
            slug=slug, status=BlogPost.Status.PUBLISHED, published_at__isnull=False
        ).first()
        if not post:
            return Response({"detail": "Not found."}, status=404)
        return Response(
            BlogPostDetailSerializer(post, context={"request": request}).data
        )


class ProcessView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "steps": PROCESS_STEPS,
                "updated_at": timezone.localtime(timezone.now()).isoformat(),
            }
        )


# ---------------------------------------------------------------------------
# Write endpoints (JSON equivalents of the legacy HTML form posts)
# ---------------------------------------------------------------------------
class LeadCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # JSON API — no session/CSRF needed

    def post(self, request):
        seed_default_services()
        form = ProjectRequestForm(request.data)
        if not form.is_valid():
            return Response({"errors": form.errors}, status=400)
        project = form.save()
        generate_quote(project)
        assign_best_developers(project)
        notify_admins_for_project(project)
        return Response(
            {
                "id": project.id,
                "status": project.status,
                "estimated_min": project.estimated_min,
                "estimated_max": project.estimated_max,
                "message": "Project brief saved. We will review it and follow up.",
            },
            status=201,
        )


class DeveloperApplicationCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        form = DeveloperApplicationForm(request.data)
        if not form.is_valid():
            return Response({"errors": form.errors}, status=400)
        application = form.save()
        notify_admins_for_developer(application)
        return Response(
            {
                "id": application.id,
                "message": "Developer application saved. We will review your portfolio.",
            },
            status=201,
        )
