# Milestone 3 — Lead capture + BANT scoring

## What's new in the app

- **Public "Get started" form** (`/leads/new/`) — anyone can submit an enquiry from
  your website. It asks friendly qualifying questions (budget / authority / need /
  timeline) that feed BANT scoring automatically — no manual scoring UI.
- **Instant auto-rating** — on submit, the lead is scored Hot / Warm / Cold (BANT
  0–12) and stamped with the **right owner** by territory (e.g. Nairobi → Brian,
  Nakuru/Kisumu → Tati).
- **Automatic thank-you email** — the prospect gets a confirmation email naming
  their assigned specialist, and the rep is notified internally. (Console email
  backend in dev; real SMTP via env vars in prod.)
- **Leads list** (front office, `CRM → Leads`) — every lead with its rating badge,
  BANT score, owner, and a one-click **Convert** to Contact. Filterable by Hot/Warm/Cold.
- **Lead detail** — full BANT breakdown (Budget / Authority / Need / Timeline) plus
  source, territory, and the original message.
- **Convert to Contact** — promotes a lead into the 360° hub (with a linked Account
  when a company is given), carrying the original message into an activity.

## Implementation detail

### Files changed / created
- `crm/services.py` — added `send_lead_autoresponse()` (lead confirmation + rep
  notification via `send_mail`) and `intake_lead()` orchestrator (score + route +
  auto-respond, idempotent on `auto_responded`).
- `crm/api.py` — `LeadIntakeView` now calls `services.intake_lead()` (sends the real
  email) instead of the old stub that only flagged `auto_responded`.
- `crm/forms.py` — added `PublicLeadForm` (ModelForm + 4 `TypedChoiceField` BANT
  questions 1–3). Slate token styling.
- `crm/views.py` — `lead_intake` (public, HTMX thanks partial), `lead_list`,
  `lead_detail`, `lead_convert` (HTMX badge swap).
- `crm/urls.py` — `leads/new/`, `crm/leads/`, `crm/leads/<pk>/`, `crm/leads/<pk>/convert/`.
- `templates/crm/lead_form.html`, `_lead_form.html`, `lead_thanks.html`,
  `_lead_thanks.html`, `lead_list.html`, `lead_detail.html`, `_lead_status.html` (new).
- `templates/crm/base.html` — added **Leads** nav item.
- `templates/crm/dashboard.html` — retrofitted from the old `zinc` palette to the
  Slate token system (it was missed in the M1→Slate retrofit) + "New lead form" CTA.

### Bugs found & fixed during verification
1. **NameError: `Tenant` is not defined** — `lead_intake` used `Tenant` without
   importing it. Fixed the model import.
2. **URL name collision** — both the public server view and the JSON API were named
   `lead_intake`. `{% url 'crm:lead_intake' %}` resolved to the **API** endpoint, so
   the HTMX form posted to `/api/crm/leads/` and returned raw JSON instead of the
   "Thanks" card. Renamed the API route to `lead_intake_api`. Verified the form now
   swaps to the proper confirmation UI in-browser.

### Decisions / deviations
- PRD explicitly excludes a manual BANT entry UI, so the public form asks 4 friendly
  qualifying questions whose option values (1–3) map directly to the BANT fields.
- Auto-responder uses Django `send_mail` with a `console` backend in dev (emails
  print to the runserver log) and real SMTP via `EMAIL_*` env vars in prod — no code
  change needed to go live.
- Territory→owner routing is hardcoded in `services.DEFAULT_TERRITORY_OWNERS`
  (noted in the service as a future Tenant config row) — matches the existing design.

## Verified
- `manage.py check` clean.
- **Public intake (HTMX, in-browser)**: submitted form → swapped to "Thanks, Browser!"
  card with Hot badge + owner Brian Mukwe; lead persisted with `auto_responded=True`.
- **Auto-responder email**: console backend printed the full confirmation email to
  `grace@nairobi.co.ke` (and rep notification) — "auto-reply sent" confirmed.
- **BANT scoring + routing**: Amina (Nakuru) → Hot/BANT 11 → Tati; Kevin (Kisumu) →
  Warm/BANT 6 → Tati; Asha (Nairobi) → Hot/BANT 12 → Brian.
- **Leads list + HTMX convert**: convert returned 200, swapped to "Converted" badge,
  set `converted_contact`, created the Contact.
- Visual: Slate/violet design consistent; BANT 2×2 grid on the form confirmed polished.

## Next milestone (M4)
- Opportunity pipeline Kanban: board + list views, drag deals across stages
  (persisted), reorder within a column, forecast. Depends on the `Opportunity` model
  already in place.
