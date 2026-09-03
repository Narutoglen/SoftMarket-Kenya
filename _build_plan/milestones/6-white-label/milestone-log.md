# Milestone 6 — White-label config + integration hooks

## What's new in the app

- **White-label Settings page** (new "Settings" nav item) — one screen to
  re-skin and configure an instance:
  - *Branding*: instance name, logo URL, primary + accent colors (live via the
    existing `--accent` / `--accent2` CSS tokens).
  - *Pipeline stages*: per-tenant ordered stages with editable labels + win-%
    + Won/Lost flags. Keys are stable slugs, so renaming a stage never breaks
    existing deals.
  - *Integrations*: M-Pesa / WhatsApp / eTIMS / Offline-sync toggles per tenant.
- **Per-tenant pipeline** — the Kanban board + forecast now render from each
  tenant's `TenantStage` config instead of the hard-coded enum, so a second
  client gets its own stages, colors, and probabilities (no code fork).
- **Outbound integration queue** — an `IntegrationMessage` model + enqueue
  service proves the delivery path for every channel (no live third-party
  calls; a worker drains the queue later).
- **Second tenant proof** — `GreenVault Foods` (slug `greenvault`) is seeded as
  a fully separate instance: emerald/amber branding, its own 5-stage pipeline
  (New Lead → Qualified → Quote Sent → Closed Won → Closed Lost), M-Pesa +
  WhatsApp enabled, and isolated data (its own contact + deal).

## Done-when — verified ✅
A second tenant (new row + stages/branding) renders **isolated**, **branded**,
and **integration-ready**. Proven in the browser at `/crm/?instance=greenvault`:
different title/colors, custom stages, GreenVault-only data (1 contact, KSh
480k pipeline), zero SoftMarket leakage.

## Implementation detail

### Files changed / created
- `crm/models.py` — added `TenantStage` (per-tenant configurable stages),
  `IntegrationConfig` (per-tenant channel toggles; `unique_together =
  [tenant, channel]` — **not** globally unique, so every tenant has its own
  four channels), `IntegrationMessage` (outbound queue: channel/recipient/
  payload/status).
- `crm/migrations/0003_*` (new models) + `0004_*` (channel unique_together fix).
- `crm/services.py` — `ensuyour_resend_api_key_here(tenant)`,
  `enqueue_integration_message(tenant, channel, recipient, payload)`,
  `tenant_stages(tenant)` (falls back to a default 6-stage pipeline for new
  tenants). Removed now-unused `DEFAULT_STAGE_PROBABILITY` (pipeline uses
  per-tenant stage probabilities).
- `crm/views.py` — `crm_settings` (GET), `crm_settings_save` (POST: branding +
  upsert stages + integration toggles), `integration_send` (POST: demo enqueue
  → JSON). Refactored `pipeline_board` / `pipeline_list` / `opportunity_move` to
  drive off `services.tenant_stages()` so the board is tenant-aware.
- `crm/urls.py` — `crm/settings/`, `crm/settings/save/`, `crm/integrations/send/`.
- `templates/crm/base.html` — added **Settings** nav item.
- `templates/crm/settings.html` — branding + stages editor + integration
  toggles + live outbound-queue demo (HTMX enqueue).
- `crm/seed.py` — `seed_second_tenant()` (GreenVault: branding, stages,
  integrations, isolated demo data); SoftMarket now also gets its 4
  `IntegrationConfig` rows.
- `crm/management/commands/seed_crm.py` — seeds both tenants.

### Bugs found & fixed during M6
- **`IntegrationConfig.channel` was `unique=True`** (globally) → seeding the 2nd
  tenant's channels collided with the 1st on re-seed (`UNIQUE constraint
  failed`). Fixed to `unique_together = [tenant, channel]` so each tenant has
  its own set of four channels. New migration `0004`.
- **Confirm modal hard-freeze** (carried from earlier): re-applied as a
  Promise-based `htmx.config.confirm` override (the `htmx:confirm` +
  `issueRequest()` approach re-triggered HTMX's native `window.confirm()` and
  froze the page). Now non-blocking. (Note: the headless browser *tool* still
  waits while a modal is open, since the click promise is pending — that's the
  tool, not a user-facing freeze; a real user clicks Confirm and it proceeds.)

### Explicitly NOT done (per PRD M6 exclusions)
- Live third-party calls for each channel (contracts wired; real creds per
  tenant later).
- Full SSO / multi-user (single shared front-office session for now).
- A worker/celery to drain `IntegrationMessage` (queue + enqueue proven;
  delivery deferred).

## Verified
- `pyflakes` clean; `manage.py check` 0 issues; both migrations applied.
- Second tenant (`?instance=greenvault`) renders isolated + emerald/amber +
  custom stages (vision-confirmed).
- Settings page shows branding editor, per-tenant stages, 4 integration toggles.
- Integration enqueue: `POST /crm/integrations/send/` → 200, creates a
  `pending` `IntegrationMessage` scoped to the tenant.
- SoftMarket + GreenVault each have their own 4 `IntegrationConfig` rows.

## PRD status
**All 6 milestones complete.** The white-label CRM core is resellable: a new
client = a `Tenant` row (+ optional `TenantStage`/`IntegrationConfig` rows),
not a code fork.
