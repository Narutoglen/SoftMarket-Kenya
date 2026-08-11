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
    path("crm/opportunities/<int:pk>/", views.opportunity_detail, name="opportunity_detail"),
    path("crm/opportunities/<int:pk>/tasks/", views.opportunity_task_create, name="opportunity_task_create"),
    path("crm/opportunities/<int:pk>/invoices/", views.opportunity_invoice_create, name="opportunity_invoice_create"),
    path("crm/opportunities/<int:pk>/invoices/<int:invoice_pk>/pay/", views.opportunity_pay_request, name="opportunity_pay_request"),
    # --- Per-tenant login gate (plan a) ---
    path("crm/login/", views.tenant_login, name="tenant_login"),
    path("crm/client-access/", views.client_access, name="client_access"),
    path("crm/login/submit/", views.tenant_login_submit, name="tenant_login_submit"),
    path("crm/logout/", views.tenant_logout, name="tenant_logout"),
    path("crm/onboarding/clear-sample/", views.clear_sample_data_view, name="clear_sample_data"),
    path("crm/onboarding/dismiss-tour/", views.dismiss_tour, name="dismiss_tour"),
    # --- Follow-ups + churn (Milestone 5) ---
    path("crm/followups/", views.followups, name="followups"),
    path("crm/followups/<int:pk>/toggle/", views.followup_toggle, name="followup_toggle"),
    path("crm/contacts/<int:pk>/lifecycle/", views.contact_lifecycle, name="contact_lifecycle"),
    # --- White-label config (Milestone 6) ---
    path("crm/settings/", views.crm_settings, name="crm_settings"),
    path("crm/settings/save/", views.crm_settings_save, name="crm_settings_save"),
    path("crm/integrations/send/", views.integration_send, name="integration_send"),
    # --- M7: the agent console ---
    path("crm/agent/", views.agent_inbox, name="agent_inbox"),
    path("crm/agent/run/", views.agent_run_now, name="agent_run_now"),
    path("crm/agent/sweep/", views.agent_sweep, name="agent_sweep"),
    path("crm/agent/suggestions/<int:pk>/", views.suggestion_decide, name="suggestion_decide"),
    path("crm/agent/questions/<int:pk>/", views.question_answer, name="question_answer"),
    # --- Bonus 1: data trust + decay radar ---
    path("crm/trust/", views.trust_dashboard, name="trust_dashboard"),
    path("crm/trust/verify/", views.trust_queue_verification, name="trust_queue_verification"),
    # --- Bonus 2: payments-aware pipeline ---
    path("crm/payments/", views.payments_console, name="payments_console"),
    path("crm/payments/ingest/", views.payment_ingest, name="payment_ingest"),
    path("crm/payments/<int:pk>/resolve/", views.payment_resolve, name="payment_resolve"),
    # Server-to-server: Safaricom Daraja C2B confirmation.
    path("hooks/mpesa/confirmation/", views.mpesa_confirmation, name="mpesa_confirmation"),
    # --- Bonus 3: client-facing deal rooms ---
    path("crm/rooms/", views.deal_rooms, name="deal_rooms"),
    path("crm/rooms/open/<int:opportunity_pk>/", views.deal_room_create, name="deal_room_create"),
    path("crm/rooms/<int:pk>/toggle/", views.deal_room_toggle, name="deal_room_toggle"),
    # The buyer-facing page lives off /crm/ on purpose — it is not the CRM.
    path("room/<str:token>/", views.deal_room_public, name="deal_room_public"),
    path("room/<str:token>/accept/", views.deal_room_accept, name="deal_room_accept"),

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

    # --- M7 + bonuses: agent, trust and payments over JSON ---
    path("api/crm/agent/tasks/", api.AgentTaskView.as_view(), name="agent_tasks_api"),
    path("api/crm/agent/runs/", api.AgentRunListView.as_view(), name="agent_runs_api"),
    path("api/crm/agent/suggestions/", api.SuggestionListView.as_view(), name="suggestions_api"),
    path(
        "api/crm/agent/suggestions/<int:pk>/",
        api.SuggestionDecideView.as_view(), name="suggestion_decide_api",
    ),
    path("api/crm/trust/", api.TrustView.as_view(), name="trust_api"),
    path("api/crm/payments/", api.PaymentView.as_view(), name="payments_api"),
]
