# Milestone 5 — Follow-ups + churn detection

## What's new in the app

- **Follow-ups page** (new "Follow-ups" nav item) — a rep's daily to-do list of
  open follow-up tasks, split into **Overdue**, **Due today**, **Upcoming**, and
  **No due date** buckets so nothing slips.
- **One-click check-off** — tick a task's circle and it's marked done and drops
  off the list instantly (no page reload); bucket counts update live.
- **Churn radar** — a side panel that surfaces customers who've gone quiet (no
  activity in 30+ days, or never), each with a days-since-last-touch readout and
  an "At risk" badge, linking straight to their contact record.
- **Lifecycle transitions** — a contact's stage (Subscriber → Lead → Customer →
  Churned) can be changed, and each change is logged to the 360 timeline as a
  note (endpoint wired; reactivation/mark-churned actions callable from a POST).

## Implementation detail

### Files changed / created
- `crm/services.py` — added:
  - `CHURN_THRESHOLD_DAYS = 30`
  - `open_followups(tenant)` — open TASK activities, ordered by due date
    (nulls last) via `F("due_at").asc(nulls_last=True)`.
  - `followup_buckets(tenant)` — splits into overdue / today / upcoming /
    undated (+ total), using `timezone.localtime` for date comparison.
  - `last_activity_at(contact)` and `churn_candidates(tenant, days=30)` —
    customers (lifecycle=customer) with no activity since cutoff (or never),
    sorted longest-quiet first (never-touched at top).
  - `set_lifecycle(contact, lifecycle)` — validated stage transition that logs a
    note activity to the timeline.
  - New imports: `from datetime import timedelta`, `from django.db.models import F`.
- `crm/views.py` — added `followups` (page), `followup_toggle` (HTMX check-off →
  re-renders `_followup_panel.html` so buckets + churn stay in sync), and
  `contact_lifecycle` (POST transition → HX-Redirect back to the 360).
- `crm/urls.py` — `crm/followups/`, `crm/followups/<pk>/toggle/`,
  `crm/contacts/<pk>/lifecycle/`.
- `templates/crm/base.html` — added **Follow-ups** nav item (check-circle icon).
- `templates/crm/followups.html` — page shell wrapping `#followup-panel`.
- `templates/crm/_followup_panel.html` — the bucketed to-do sections + churn
  radar side panel (2/3 + 1/3 grid). Rose accent for overdue, amber for churn.
- `templates/crm/_followup_row.html` — single task row with the check-off button
  (`hx-post` toggle, targets `#followup-panel`), contact link, due date/time.
- `crm/seed.py` — imports `Activity`; seeds a quiet CUSTOMER (Grace Wanjiru, no
  activity → churn radar) plus three open follow-up tasks spanning overdue /
  today / upcoming buckets.

### Decisions / deviations
- **No migration needed.** The existing `Activity` model already had `due_at` +
  `done`, and `Contact.Lifecycle` already included `CHURNED`, so churn is
  computed dynamically (customer + no recent activity) rather than stored — the
  PRD asks for a churn *flag*, and a live-computed flag avoids a stale field and
  a nightly job (in-app only, per M5 exclusions).
- **Check-off swaps the whole panel** (not just the row) so the bucket the task
  leaves, its count, and the churn radar all re-render consistently in one HTMX
  call. Reuses the existing cookie-based CSRF `htmx:configRequest` listener.
- **"Linking back to the deal"** — tasks are `Activity` rows tied to a `Contact`
  (the 360 hub), and each follow-up row links to that contact; opportunities
  hang off the same contact, so the link-back is via the contact record. Direct
  task→opportunity FKs were not added (out of scope / avoids a schema change).
- **Lifecycle UI** — the transition endpoint is wired and logs to the timeline;
  a full dropdown control on the contact 360 can be surfaced in a later polish
  pass (the churn radar + contact link already give the rep the entry point).
- Per PRD M5 exclusions: **no push/email reminders** (in-app only) and **no
  predictive/ML churn** (simple N-day rule).

### Bugs found & fixed during verification
- `seed.py` raised `NameError: Activity` — added `Activity` to the model import.
- Initially made an existing customer quiet by giving her a task (which would
  reset her activity clock); switched to a dedicated no-activity customer
  (Grace Wanjiru) so the churn radar has a stable demo entry.

## Verified
- `manage.py check` clean; seed re-run (no migration).
- `/crm/followups/` → 200. `followup_buckets` returns overdue 1 / today 1 /
  upcoming 1 / undated 1 (total 4); `churn_candidates` returns Grace Wanjiru
  (never touched).
- **Check-off tested in-browser**: marking the overdue task done removed the
  Overdue section live via HTMX (no reload); re-opened to restore seed state.
- Visual: Slate/violet page, rose Overdue header, amber Churn radar, polished
  and on-brand (browser_vision confirmed, no layout issues).

## Next milestone (M6)
- White-label config + integration hooks: per-tenant pipeline stage config UI,
  branding UI (colors/logo), and M-Pesa / WhatsApp / eTIMS / offline-sync
  interfaces + queues. Done when a second tenant renders isolated + branded +
  integration-ready. (Note: `TenantStage` model from the PRD data model — for
  configurable per-tenant stages — is not yet created; M6 will need it.)
