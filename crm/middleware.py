"""Per-tenant access gate backed by real Django auth.

* Public tenant (is_public=True)  -> always open. A prospect browsing the
  SoftMarket site NEVER sees a login.
* Private tenant (paying client)  -> the visitor must be authenticated AND a
  member of that tenant (enforced via request.user + TenantMembership). This is
  real per-user auth, not the old shared access code.
* The login page + the public lead-intake form are explicitly exempt.
* HTMX requests get an `HX-Redirect` header (so the SPA-style UI navigates)
  instead of a bare 302.
"""

from django.http import HttpResponse
from django.shortcuts import HttpResponseRedirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from .api import resolve_tenant

# Paths that must stay open even for private tenants.
PUBLIC_PATHS = {
    "/leads/new/",          # public web-intake form (prospects submit leads)
}


class TenantAccessMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        path = request.path

        # Only gate the HTML front office; leave /api/ (DRF IsAuthenticated) and
        # admin to their own rules.
        if not path.startswith("/crm/"):
            return None
        if path in PUBLIC_PATHS:
            return None
        # Don't gate the login page itself (avoids a redirect loop).
        login_path = reverse("crm:tenant_login")
        if path == login_path:
            return None

        tenant = resolve_tenant(request)
        if tenant is None:
            return None  # view will 404; not our job to decide here.

        if tenant.is_public:
            return None

        # Private tenant: require an authenticated member.
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return None  # resolve_tenant already validated membership

        # Not authenticated -> send to login.
        target = f"{login_path}?instance={tenant.slug}"
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Redirect"] = target
            return response
        return HttpResponseRedirect(target)
