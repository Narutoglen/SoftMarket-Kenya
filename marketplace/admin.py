from django.contrib import admin

from .models import (
    Assignment,
    BlogPost,
    DeveloperApplication,
    DeveloperProfile,
    NotificationLog,
    Payment,
    ProjectRequest,
    ServiceCategory,
)
from .services import (
    MpesaClient,
    assign_best_developers,
    create_deposit_payment,
    create_developer_from_application,
    generate_quote,
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "min_price", "max_price", "deposit_amount", "monthly", "active")
    list_filter = ("active", "monthly")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")


@admin.register(DeveloperProfile)
class DeveloperProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "stack", "availability_score", "quality_score")
    list_filter = ("status", "service_categories")
    filter_horizontal = ("service_categories",)
    search_fields = ("name", "email", "phone", "stack")


@admin.action(description="Convert selected applications into developer profiles")
def convert_to_profiles(modeladmin, request, queryset):
    for application in queryset:
        create_developer_from_application(application)


@admin.register(DeveloperApplication)
class DeveloperApplicationAdmin(admin.ModelAdmin):
    list_display = ("name", "stack", "portfolio_url", "converted_profile", "created_at")
    search_fields = ("name", "stack", "portfolio_url")
    actions = [convert_to_profiles]


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    autocomplete_fields = ("developer",)


@admin.action(description="Suggest best developer matches")
def suggest_matches(modeladmin, request, queryset):
    for project in queryset:
        assign_best_developers(project)


@admin.action(description="Initiate M-Pesa booking deposit STK push")
def initiate_deposit_stk(modeladmin, request, queryset):
    mpesa = MpesaClient()
    for project in queryset:
        if not project.deposit_amount:
            generate_quote(project)
        payment = create_deposit_payment(project)
        mpesa.initiate_stk_push(payment)


@admin.register(ProjectRequest)
class ProjectRequestAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "service_label",
        "budget",
        "timeline",
        "deposit_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "service", "utm_source", "created_at")
    search_fields = ("name", "phone", "email", "service_label", "details")
    readonly_fields = ("estimated_min", "estimated_max", "deposit_amount", "created_at", "updated_at")
    inlines = [AssignmentInline]
    actions = [suggest_matches, initiate_deposit_stk]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("project", "developer", "score", "status", "created_at")
    list_filter = ("status", "developer__status")
    search_fields = ("project__name", "developer__name", "developer__stack")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("project", "amount", "phone", "status", "mpesa_receipt", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("project__name", "phone", "checkout_request_id", "mpesa_receipt")
    readonly_fields = ("callback_payload", "merchant_request_id", "checkout_request_id")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("channel", "recipient", "subject", "success", "created_at")
    list_filter = ("channel", "success", "created_at")
    search_fields = ("recipient", "subject", "message", "provider_response")


@admin.action(description="Publish selected blog posts")
def publish_blog_posts(modeladmin, request, queryset):
    from django.utils import timezone

    queryset.update(status=BlogPost.Status.PUBLISHED, published_at=timezone.now())


@admin.action(description="Unpublish selected blog posts")
def unpublish_blog_posts(modeladmin, request, queryset):
    queryset.update(status=BlogPost.Status.DRAFT)


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author_name", "status", "published_at", "updated_at")
    list_filter = ("status", "category", "content_image_placement", "published_at")
    search_fields = ("title", "category", "author_name", "author_role", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    actions = [publish_blog_posts, unpublish_blog_posts]
