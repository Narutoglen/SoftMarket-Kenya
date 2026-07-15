from django.urls import path

from . import api

app_name = "crm"

urlpatterns = [
    # Public intake + lists
    path("api/crm/leads/", api.LeadIntakeView.as_view(), name="lead_intake"),
    path("api/crm/leads/", api.LeadListView.as_view(), name="lead_list"),
    path("api/crm/contacts/", api.ContactListView.as_view(), name="contact_list"),
    path("api/crm/contacts/<int:pk>/", api.ContactDetailView.as_view(), name="contact_detail"),
    path("api/crm/contacts/<int:pk>/activities/", api.ActivityCreateView.as_view(), name="activity_create"),
    path("api/crm/accounts/", api.AccountListView.as_view(), name="account_list"),
    path("api/crm/opportunities/", api.OpportunityListView.as_view(), name="opportunity_list"),
    path("api/crm/pipeline/", api.PipelineView.as_view(), name="pipeline"),
    path("api/crm/leads/<int:pk>/convert/", api.LeadConvertView.as_view(), name="lead_convert"),
    path("api/crm/contacts/merge/", api.ContactMergeView.as_view(), name="contact_merge"),
]
