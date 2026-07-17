# Milestone 2 — Activity log + 360° timeline write path

## What's new

- **Log activity inline** on the contact 360 page — an HTMX `<details>` form
  (type / subject / notes / due) that posts and redirects back to the detail
  view, re-rendering the timeline. No full-page reload.
- **Task `done` toggle** — each `task` row has an HTMX checkbox button that
  flips `Activity.done` and swaps just that `<li>` (with strikethrough + filled
  checkbox when done). Verified working in-browser.
- **Slate token fix** — `forms.py` INPUT widget classes were still the old
  `zinc` palette from the first M1 pass; corrected to the Slate token classes
  (`bg-[var(--surface)]`, `border-[var(--hairline)]`, `text-[var(--ink-display)]`,
  `focus:border-[var(--accent)]`) so form inputs match the pages.
- **App-wide CSRF for HTMX** — added an `htmx:configRequest` listener in
  `base.html` that reads `csrftoken` from the cookie and attaches it to every
  HTMX request. Without this, in-browser delete/toggle buttons (which have no
  enclosing `{% csrf_token %}`) hit a 403. The curl tests passed because the
  token was passed manually, masking the gap — caught by the live browser test.

## Implementation detail

- **Files changed**
  - `crm/forms.py` — Slate INPUT classes + new `ActivityForm` (type/subject/notes/due_at/done).
  - `crm/views.py` — `activity_create` (HTMX, returns `HX-Redirect` or partial on error) + `activity_toggle` (HTMX, swaps `_activity_row.html`).
  - `crm/urls.py` — `crm/contacts/<contact_pk>/activities/new/` and `crm/activities/<pk>/toggle/`.
  - `templates/crm/contact_detail.html` — inline form include + timeline loop now passes `with activity=a` to `_activity_row.html` (bug fix: the loop var was `a`, the partial expected `activity`).
  - `templates/crm/_activity_form.html` (new) — inline HTMX log form.
  - `templates/crm/_activity_row.html` (new) — timeline row; task rows get the HTMX toggle button.
  - `templates/crm/base.html` — `htmx:configRequest` CSRF listener.

## Bugs found & fixed during verification

1. **Empty timeline** — `_activity_row.html` used `activity` but the detail loop
   var was `a`; rows rendered blank (`id="activity-"`). Fixed with `with activity=a`.
2. **In-browser 403 on toggle/delete** — no `{% csrf_token %}` in scope for
   header/row buttons. Fixed app-wide via the `htmx:configRequest` listener.

## Verified

- `manage.py check` clean.
- **Create (HTMX, inline form)**: POST → `HX-Redirect: /crm/contacts/7/`, persisted (activities 2→3), then cleaned.
- **Toggle (HTMX, in-browser)**: clicked task button → `done` flipped True → fresh page load shows struck-through text + filled purple checkbox (screenshot-confirmed).
- **CSRF**: toggle works in-browser after the `htmx:configRequest` fix (was 403 before).
- Visual: Slate palette + violet accent consistent on the detail page and forms.

## Next milestone (M3)

- Leads: intake (already have `api.LeadIntakeView` + `LeadConvertView`) + the
  BANT score → rating pipeline, shown on a Leads list with convert-to-contact.
- Tie activities to leads too (currently contact-only).
