# Milestone 1 — Tenant + Contact/Account CRUD

## What's new in the app

- **Front-office UI for the CRM** at `/crm/` (dashboard, contacts, accounts), styled in a polished design system that follows the BM design-system tokens translated to Django templates.
- **Dashboard** — tenant-scoped stat tiles (Contacts, Open pipeline KSh, Hot leads, Tasks due) + recent contacts.
- **Contacts** — HTMX live-search list, 360° detail with vertical activity timeline, HTMX create/edit/delete.
- **Accounts** — HTMX live-search list, detail with linked contacts, HTMX create/edit/delete.
- **White-label branding** — every page reads accent colors from the active `Tenant` (`brand_primary_color` / `brand_accent_color`) via CSS vars, so a second tenant re-skins automatically.
- **`python manage.py seed_crm`** — idempotent seed + demo timeline data for local preview.

## Framework compliance (PRD line 7: "Django + PostgreSQL/Supabase, Tailwind, HTMX, deployed on Vercel")

- ✅ **Django** — server-rendered templates (no separate SPA; reviews happen on the dev server).
- ✅ **Tailwind** — via Play CDN in dev; design tokens translated from the BM `bm-design-system` skill.
- ✅ **HTMX** — `django-htmx` installed (app + `HtmxMiddleware`); live search (debounced `input`), form submits (`hx-post` + `HX-Redirect` on success / partial swap on validation error), and inline delete (`hx-post` + `hx-confirm`) are all HTMX. No full-page reloads for these actions.
- Design tokens (Slate neutral `page/surface/hairline/ink-*`, `accent` = tenant brand, `signal` = amber) taken from `bm-design-system/references/derive-palette.md` and applied as CSS vars + Tailwind arbitrary values. The React `.tsx` primitives in that skill are a **reference design language only** — translated into Django markup, not pasted.

## Implementation detail

- **Files created**
  - `crm/forms.py` — `ContactForm`, `AccountForm` (styled widgets; `tenant` never a field).
  - `crm/views.py` — dashboard + contact/account list/detail/form/delete. All tenant-scoped via `resolve_tenant` (same `X-CRM-Instance` / `?instance=` as the API). HTMX-aware: list/delete return partials or `HX-Redirect`; forms swap in place.
  - `crm/urls.py` — `/crm/...` front-office routes kept alongside the `/api/crm/...` API routes (API names suffixed `_api`).
  - `crm/management/commands/seed_crm.py` — idempotent seed.
  - `templates/crm/` — `base.html` + dashboard/contact/account list/detail/form templates + HTMX partials (`_contact_rows.html`, `_contact_search.html`, `_contact_form.html`, `_account_rows.html`).
- **Model additions** — `Contact.get_absolute_url()` and `Account.get_absolute_url()` (used by HTMX redirects).
- **Config** — added `django-htmx` to `requirements.txt`, `INSTALLED_APPS`, and `MIDDLEWARE`.

## Decisions

- **Server-rendered Django templates, not the Next.js/HTMX SPA from the PRD.** The project has no frontend framework wired and Glen reviews on the dev server, so templates are the lowest-friction working path. HTMX gives the snappy UX without a JS build step.
- **No model changes needed** beyond `get_absolute_url` — `Tenant`, `Contact`, `Account`, `Activity` already existed. `TenantStage` (per-tenant pipelines) deferred to Milestone 6.

## Verified

- `manage.py check` clean; `seed_crm` idempotent.
- Dev server (127.0.0.1:8000) returns HTTP 200 for dashboard, contact list, contact create, account list.
- **HTMX verified in-browser:** live search filters the list in place (no reload); form submit returns `HX-Redirect` and lands on the detail page; delete uses `hx-confirm`.
- **Write path verified:** HTMX POST created a contact → redirected to detail → appeared in tenant-scoped list (then cleaned up).
- Visual preview confirmed (Slate palette + violet branding, polished).

## Next milestone needs

- Activity logging is currently view-only (seeded data). Milestone 2 adds the create form + task `done` toggle wired to the timeline (HTMX).
