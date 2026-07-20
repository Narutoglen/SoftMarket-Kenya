"""Per-tenant access gate (plan a): public tenants stay open, private tenants
require a tenant login session.

Applied as middleware so every HTML front-office path is covered consistently
without decorating 28 views by hand. Behaviour:

* Public tenant (is_public=True)  -> always open. A prospect browsing the
  SoftMarket site NEVER sees a login.
* Private tenant (paying client)  -> redirect to the tenant login page unless
  the visitor has an authenticated `crm_tenant` session for that slug.
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

        # Only gate the HTML front office; leave /api/ and admin to their own rules.
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

        if request.session.get("crm_tenant") == tenant.slug:
            return None  # authenticated into this private tenant

        # Private + not authenticated -> send to login.
        target = f"{login_path}?instance={tenant.slug}"
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Redirect"] = target
            return response
        return HttpResponseRedirect(target)
