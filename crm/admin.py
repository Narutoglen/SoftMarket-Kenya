from django.contrib import admin

from .models import Account, Activity, Contact, Lead, Opportunity, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "created_at")
    search_fields = ("name", "slug")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "tenant", "lifecycle", "territory", "created_at")
    list_filter = ("tenant", "lifecycle")
    search_fields = ("first_name", "last_name", "email", "phone")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "industry", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name", "industry")


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("full_name", "rating", "owner", "source", "tenant", "created_at")
    list_filter = ("tenant", "rating", "source")
    search_fields = ("first_name", "last_name", "email", "company")


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("name", "stage", "amount", "owner", "tenant", "created_at")
    list_filter = ("tenant", "stage")
    search_fields = ("name", "owner")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("contact", "type", "subject", "done", "tenant", "created_at")
    list_filter = ("tenant", "type", "done")
