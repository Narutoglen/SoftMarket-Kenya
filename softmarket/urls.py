from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("marketplace.urls")),
    path("", include("crm.urls")),
]

# Serve collected static files in ALL environments.
# WhiteNoise is not intercepting /static/ under the Vercel Python WSGI
# handler, so we register the static route explicitly. Files exist at
# STATIC_ROOT (staticfiles/) on the deployed lambda.
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
