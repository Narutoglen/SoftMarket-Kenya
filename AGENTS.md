# SoftMarket KE — Agent Instructions

This file gives coding agents (Hermes, Codex, Claude Code) durable context for the SoftMarket KE codebase.

## Project

Single Django project `D:\GlenTech\SOFTSTORE.KE` (github.com/Narutoglen/SoftMarket-Kenya, Vercel 'softmarket-kenya'). JSON API at `/api/*`. No Next.js. A white-label CRM core: one reusable CRM codebase serves multiple retail clients as configured `Tenant` instances (SoftMarket is tenant #1). Contact-centric 360° model: `Tenant → Account / Contact → Activity / Lead / Opportunity`.

## The agentic layer (`crm/agent/`)

Ported from trycompai/crm. Read `crm/agent/__init__.py` for the layout, then
`crm/agent/evidence.py` — the evidence ledger is the load-bearing idea and
almost every rule you might be tempted to relax lives there.

Non-negotiables when changing this code:

- **Tools report observations, not conclusions.** A tool returns what it saw and
  where; the ledger decides what that earns. Do not add a tool that writes to a
  record directly — route it through `record_observation`.
- **`model.guess` is priced at zero and must stay there.** It is what stops
  recall reaching a customer record.
- **Judgement fields stay out of `WRITABLE_FIELDS`** — lifecycle, stage, BANT,
  deal value. Facts yes, decisions no.
- **The deterministic playbook is not a stub.** Every feature must work with no
  API key set; the Claude planner is an upgrade, never a dependency. Both drive
  the same registry in `crm/agent/tools.py`, so guard rails cannot diverge.
- **Tenant scope comes from the run context, never from a tool argument.**

The skills in `crm/agent/skills/*.md` are prompt *and* documentation — they are
versioned, reviewable, and they are what the Claude planner is held to. Update
them in the same change as the behaviour they describe.

Bonus features that hang off the same provenance: `crm/trust.py` (trust score +
decay radar), `crm/payments.py` (M-Pesa reconciliation), `crm/dealroom.py`
(client-facing deal rooms).

## `_build_plan/`

The `_build_plan/` folder contains the initial PRD and per-milestone prompts used to scaffold this codebase during its initial build-out phase. These files are **temporary** — they exist for documentation and guidance only. They are **not** functional: no code, configuration, or runtime logic in this codebase should import, reference, or depend on anything inside `_build_plan/`.

Do not treat `_build_plan/` as long-living documentation for the codebase. The codebase will evolve past the assumptions and decisions captured here. Once the initial milestones are complete, this folder is expected to be deleted.
