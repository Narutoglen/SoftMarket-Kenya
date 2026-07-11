from django.contrib.sitemaps.views import sitemap
from django.urls import path

from . import api, views
from .seo import BlogSitemap, StaticViewSitemap, robots_txt

app_name = "marketplace"

sitemaps = {
    "static": StaticViewSitemap,
    "blog": BlogSitemap,
}

urlpatterns = [
    # --- SEO ---
    path("robots.txt", robots_txt, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    # --- JSON API (consumed by the Next.js frontend) ---
    path("api/services/", api.ServiceListView.as_view(), name="api_services"),
    path("api/blog/", api.BlogListView.as_view(), name="api_blog_list"),
    path("api/blog/<slug:slug>/", api.BlogDetailView.as_view(), name="api_blog_detail"),
    path("api/process/", api.ProcessView.as_view(), name="api_process"),
    path("api/leads/", api.LeadCreateView.as_view(), name="api_leads"),
    path(
        "api/developer-applications/",
        api.DeveloperApplicationCreateView.as_view(),
        name="api_developer_applications",
    ),
    # --- Legacy server-rendered HTML (kept as fallback) ---
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
