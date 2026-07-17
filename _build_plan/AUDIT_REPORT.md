# SoftMarket Kenya CRM — Dead-Code & System Audit Report

Date: 2026-07-17
Scope: entire Django project (`crm`, `marketplace`, `softmarket`), templates,
URLs, services, static assets. Migrations and `.venv` excluded.
Tools: pyflakes 3.4.0, vulture 2.16, targeted grep/reverse() checks.

---

## 🔴 CRITICAL BUG FOUND & FIXED — duplicate URL names (root cause of "Leads page not working")

Three URL `name=`s were **defined twice** — once on the HTML front-office route
and again on the JSON API route. Django's `reverse()` resolves to the **last**
definition, so every template link silently pointed at the raw JSON API instead
of the styled page:

| URL name | `{% url %}` used by | Resolved to (BEFORE) | Fixed to (AFTER) |
|---|---|---|---|
| `lead_list` | **Leads nav link** + filter tabs | `/api/crm/leads/list/` (JSON) ❌ | `/crm/leads/` ✅ |
| `lead_convert` | Convert button | `/api/crm/leads/<pk>/convert/` ❌ | `/crm/leads/<pk>/convert/` ✅ |
| `activity_create` | Log-activity form | `/api/crm/contacts/<pk>/activities/` ❌ | `/crm/contacts/<pk>/activities/new/` ✅ |

**This is exactly why clicking "Leads" opened the DRF JSON page.**

**Fix:** every JSON API route name in `crm/urls.py` is now suffixed `_api`
(`lead_list_api`, `lead_convert_api`, `activity_create_api`, plus
`opportunity_list_api`, `pipeline_api`, `lead_intake_api` already had it). Added
a comment documenting the collision hazard. Verified via `reverse()`:

```
lead_list       -> /crm/leads/          (was /api/crm/leads/list/)
lead_convert    -> /crm/leads/1/convert/
activity_create -> /crm/contacts/1/activities/new/
lead_list_api   -> /api/crm/leads/list/
```

Confirmed in-browser: the "Leads" nav link now lands on the styled HTML page.

---

## 🟡 DEAD CODE REMOVED — unused imports (6)

All flagged by pyflakes, all confirmed unused and removed:

| File | Removed import |
|---|---|
| `crm/models.py` | `from django.utils import timezone` |
| `marketplace/api.py` | `from django.conf import settings` |
| `marketplace/seo.py` | `from django.conf import settings` |
| `marketplace/services.py` | `from datetime import datetime` |
| `marketplace/tests.py` | `from django.utils import timezone` (also removed a duplicate `TestCase` import introduced) |
| `marketplace/templatetags/static_extras.py` | `from django.templatetags.static import static` |

Post-fix: **pyflakes reports 0 issues across all apps.**

---

## 🟢 CHECKED — NOT dead (no action needed)

- **All 28 CRM views** are wired to a URL. No orphan view functions.
- **All 36 templates** are referenced (render / extends / include). No orphans.
- **All 8 marketplace templates** referenced.
- **`services.pipeline_summary`** — still used by the JSON `PipelineView` API;
  coexists with `_stage_summary` (HTML board). Both legitimately used.
- **Vulture 60%-confidence hits** (admin classes, `Meta.model`,
  `permission_classes`, `apps.py` config, management `Command`) are Django
  framework introspection points — **false positives**, not dead code.

## ⚪ UNUSED-BUT-INTENTIONAL — API url names (kept)

These `crm:` url names are defined but not `reverse()`d internally. They are the
**public JSON API** consumed by the future Next.js frontend, so they are kept by
design (not dead): `lead_list_api`, `lead_convert_api`, `activity_create_api`,
`contact_list_api`, `contact_detail_api`, `account_list_api`,
`opportunity_list_api`, `pipeline_api`, `lead_intake_api`, `contact_merge`.

## 🗒️ STRAY DEV ARTIFACT (flagged, not deleted)

- `crm_ui_preview.html` (19 KB, project root) — an early static UI mockup.
  **Untracked** in git, **not referenced** by any code, **not deployed**.
  Recommend deleting, but left in place pending your OK (harmless).

---

## VERIFICATION (all green)

- `pyflakes` (crm + marketplace + softmarket): **clean, 0 issues**
- `manage.py check`: **0 issues**
- `manage.py test marketplace`: **9/9 passed**
- Live pages: `/crm/`, `/crm/leads/`, `/crm/pipeline/`, `/crm/followups/`,
  `/crm/contacts/`, `/crm/accounts/`, `/leads/new/` → all **200**
- Browser: "Leads" nav → styled HTML page (bug fixed, confirmed)

## FILES CHANGED
- `crm/urls.py` — renamed 3 colliding API route names to `_api` (+ 3 already), comment
- `crm/models.py`, `marketplace/api.py`, `marketplace/seo.py`,
  `marketplace/services.py`, `marketplace/tests.py`,
  `marketplace/templatetags/static_extras.py` — removed unused imports

All changes uncommitted (per preview-before-commit rule).
