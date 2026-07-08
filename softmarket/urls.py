from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.urls import include, path
import os


def _debug_fs(request):
    base = settings.BASE_DIR
    static_root = settings.STATIC_ROOT
    out = []
    out.append(f"BASE_DIR: {base}")
    out.append(f"STATIC_ROOT: {static_root}")
    out.append(f"STATIC_URL: {settings.STATIC_URL}")
    try:
        out.append("BASE_DIR entries: " + ", ".join(sorted(os.listdir(base))))
    except Exception as e:
        out.append(f"BASE_DIR list err: {e}")
    try:
        sr = os.path.join(static_root, "marketplace")
        out.append("STATIC_ROOT/marketplace exists: " + str(os.path.isdir(sr)))
        if os.path.isdir(sr):
            out.append("STATIC_ROOT/marketplace: " + ", ".join(sorted(os.listdir(sr))))
    except Exception as e:
        out.append(f"STATIC_ROOT list err: {e}")
    return HttpResponse("<pre>" + "\n".join(out) + "</pre>")


urlpatterns = [
    path("__debug_fs__", _debug_fs),
    path("admin/", admin.site.urls),
    path("", include("marketplace.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
