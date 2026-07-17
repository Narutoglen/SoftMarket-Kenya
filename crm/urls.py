from django.urls import path

from . import api, views

app_name = "crm"

urlpatterns = [
    # --- Server-rendered front office (Milestone 1) ---
    path("crm/", views.dashboard, name="dashboard"),
    path("crm/contacts/", views.contact_list, name="contact_list"),
    path("crm/contacts/new/", views.contact_form, name="contact_create"),
    path("crm/contacts/<int:pk>/", views.contact_detail, name="contact_detail"),
    path("crm/contacts/<int:pk>/edit/", views.contact_form, name="contact_edit"),
    path("crm/contacts/<int:pk>/delete/", views.contact_delete, name="contact_delete"),
    path("crm/accounts/", views.account_list, name="account_list"),
    path("crm/accounts/new/", views.account_form, name="account_create"),
    path("crm/accounts/<int:pk>/", views.account_detail, name="account_detail"),
    path("crm/accounts/<int:pk>/edit/", views.account_form, name="account_edit"),
    path("crm/accounts/<int:pk>/delete/", views.account_delete, name="account_delete"),
    path("crm/contacts/<int:contact_pk>/activities/new/", views.activity_create, name="activity_create"),
    path("crm/activities/<int:pk>/toggle/", views.activity_toggle, name="activity_toggle"),
    # --- Pipeline (Milestone 4 — Kanban board + list + drag-to-move) ---
    path("crm/pipeline/", views.pipeline_board, name="pipeline_board"),
    path("crm/pipeline/list/", views.pipeline_list, name="pipeline_list"),
    path("crm/opportunities/<int:pk>/move/", views.opportunity_move, name="opportunity_move"),
    # --- Follow-ups + churn (Milestone 5) ---
    path("crm/followups/", views.followups, name="followups"),
    path("crm/followups/<int:pk>/toggle/", views.followup_toggle, name="followup_toggle"),
    path("crm/contacts/<int:pk>/lifecycle/", views.contact_lifecycle, name="contact_lifecycle"),
    # --- White-label config (Milestone 6) ---
    path("crm/settings/", views.crm_settings, name="crm_settings"),
    path("crm/settings/save/", views.crm_settings_save, name="crm_settings_save"),
    path("crm/integrations/send/", views.integration_send, name="integration_send"),
    # --- Leads (Milestone 3 — public intake + front office) ---
    path("leads/new/", views.lead_intake, name="lead_intake"),
    path("crm/leads/", views.lead_list, name="lead_list"),
    path("crm/leads/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("crm/leads/<int:pk>/convert/", views.lead_convert, name="lead_convert"),

    # --- JSON API (consumed by the Next.js frontend) ---
    # NOTE: API route names are suffixed `_api` so they never collide with the
    # HTML front-office names above. Django reverse() resolves to the LAST
    # matching name, so a duplicate here would silently shadow the HTML page
    # (that bug pointed the "Leads" nav + Convert button at the raw JSON).
    path("api/crm/leads/", api.LeadIntakeView.as_view(), name="lead_intake_api"),
    path("api/crm/leads/list/", api.LeadListView.as_view(), name="lead_list_api"),
    path("api/crm/contacts/", api.ContactListView.as_view(), name="contact_list_api"),
    path("api/crm/contacts/<int:pk>/", api.ContactDetailView.as_view(), name="contact_detail_api"),
    path("api/crm/contacts/<int:pk>/activities/", api.ActivityCreateView.as_view(), name="activity_create_api"),
    path("api/crm/accounts/", api.AccountListView.as_view(), name="account_list_api"),
    path("api/crm/opportunities/", api.OpportunityListView.as_view(), name="opportunity_list_api"),
    path("api/crm/pipeline/", api.PipelineView.as_view(), name="pipeline_api"),
    path("api/crm/leads/<int:pk>/convert/", api.LeadConvertView.as_view(), name="lead_convert_api"),
    path("api/crm/contacts/merge/", api.ContactMergeView.as_view(), name="contact_merge"),
]
