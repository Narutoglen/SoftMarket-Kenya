from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("", views.home, name="home"),
    path("work/", views.work, name="work"),
    path("about/", views.about, name="about"),
    path("process/", views.process, name="process"),
    path("blog/", views.blog_list, name="blog_list"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("dashboard/analytics/", views.analytics_dashboard, name="analytics"),
    path("dashboard/export/project-requests.csv", views.export_project_requests, name="export_project_requests"),
    path("dashboard/export/project-requests.xlsx", views.export_project_requests_xlsx, name="export_project_requests_xlsx"),
    path("payments/mpesa/stk/<int:project_id>/", views.initiate_mpesa_deposit, name="initiate_mpesa_deposit"),
    path("payments/mpesa/callback/", views.mpesa_callback, name="mpesa_callback"),
    path("payments/<int:payment_id>/status/", views.payment_status, name="payment_status"),
]
