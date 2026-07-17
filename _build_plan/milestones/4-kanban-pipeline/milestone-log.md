# Milestone 4 — Opportunity pipeline (Kanban)

## What's new in the app

- **Kanban board** — a drag-and-drop pipeline of every deal, split into six
  stages (Prospecting → Qualification → Proposal → Negotiation → Won → Lost).
  Drag any deal card to another column and it sticks.
- **Live totals + forecast** — the top of the board shows Open pipeline,
  Weighted forecast (probability-adjusted), Won, and Lost values. These
  recalculate the moment you move a deal, with no page reload.
- **Deal cards** — each card shows the deal name, value (KSh), linked contact
  and account, and the owner.
- **List view** — a flat table of all deals grouped by stage (toggle top-right
  on the board), handy for scanning values and owners.
- **Per-stage value totals** — every column header shows how many deals and how
  much value sits in that stage.

## Implementation detail

### Files changed / created
- `crm/models.py` — added `Opportunity.order` (PositiveIntegerField) for
  manual within-column ordering; `Meta.ordering` now `(stage, order, -created_at)`.
- `crm/migrations/0002_alter_opportunity_options_opportunity_order.py` — new
  migration for the `order` field.
- `crm/services.py` — added `DEFAULT_STAGE_PROBABILITY` dict (per-stage win %:
  prospecting 10, qualification 30, proposal 60, negotiation 80, won 100,
  lost 0) used by the board forecast. (Reuses the same numbers the existing
  `pipeline_summary` used, now centralised.)
- `crm/views.py` — `pipeline_board` (HTMX-aware; swaps `_pipeline_columns.html`),
  `pipeline_list`, and `opportunity_move` (HTMX POST — persists stage + ordering
  from a dropped card, then re-renders the board columns + totals live).
  Added `_stage_summary()` helper (open value, weighted forecast, won/lost).
- `crm/urls.py` — `crm/pipeline/`, `crm/pipeline/list/`,
  `crm/opportunities/<pk>/move/`.
- `templates/crm/base.html` — added **Pipeline** nav item (kanban icon).
- `templates/crm/pipeline_board.html` — board shell + forecast include.
- `templates/crm/_pipeline_forecast.html` — Open / Weighted / Won / Lost cards.
- `templates/crm/_pipeline_columns.html` — the 6 columns; each card is
  `draggable`, columns handle `dragover`/`drop`; the `moveCard()` JS fires an
  `htmx.ajax` POST to `opportunity_move`, swapping `#board-columns` in place.
- `templates/crm/pipeline_list.html` — table list view.
- `crm/seed.py` — expanded demo deals to one per stage (prospecting,
  qualification, proposal, negotiation, won, lost) so the board is populated.

### Decisions / deviations
- **Drag-and-drop = native HTML5 DnD + HTMX** (no external JS lib), matching
  the PRD's Django + Tailwind + HTMX stack. The drop handler posts stage + the
  destination column's ordered ids; the server re-persists order for the whole
  column and re-renders. Reorder-within-column is wired (the `order` param) but
  the primary verified path is cross-stage moves; intra-column drag reordering
  works the same way (drop on same column re-indexes).
- **No per-deal probability editing UI** — per the PRD's explicit M4 exclusions,
  forecast uses the fixed per-stage `DEFAULT_STAGE_PROBABILITY`.
- **Reused the existing `services.pipeline_summary` numbers** via the new
  constant so board + API stay consistent.

### Bugs found & fixed during verification
- `urls.py` edit initially dropped the `account_delete` route and duplicated
  `contact_delete`; corrected back to the proper routes.
- `services.py` patch dropped the `score_lead_rating` def line; restored.

## Verified
- `manage.py check` clean; migration `0002` applied; seed re-run.
- Board (`/crm/pipeline/`) → 200; List (`/crm/pipeline/list/`) → 200.
- **Drag-move endpoint** (`POST /crm/opportunities/<pk>/move/`) → 200, persists
  new stage, returns re-rendered board with updated per-stage totals + forecast
  (verified opp 5 prospecting → won persisted; then reset to seed state).
- Visual: Slate/violet board with 6 columns, deal cards, per-column totals, and
  the 4-metric forecast header confirmed polished in-browser.

## Next milestone (M5)
- Follow-ups + churn: to-do list of next actions with due dates, check-off
  linking back to the deal, lifecycle transitions, churn flag on silent
  customers. (Per-deal probability editing and custom fields remain out of
  scope per PRD.)
