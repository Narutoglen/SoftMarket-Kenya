# SoftMarket KE — Agent Instructions

This file gives coding agents (Hermes, Codex, Claude Code) durable context for the SoftMarket KE codebase.

## Project

Single Django project `D:\GlenTech\SOFTSTORE.KE` (github.com/Narutoglen/SoftMarket-Kenya, Vercel 'softmarket-kenya'). JSON API at `/api/*`. No Next.js. A white-label CRM core: one reusable CRM codebase serves multiple retail clients as configured `Tenant` instances (SoftMarket is tenant #1). Contact-centric 360° model: `Tenant → Account / Contact → Activity / Lead / Opportunity`.

## `_build_plan/`

The `_build_plan/` folder contains the initial PRD and per-milestone prompts used to scaffold this codebase during its initial build-out phase. These files are **temporary** — they exist for documentation and guidance only. They are **not** functional: no code, configuration, or runtime logic in this codebase should import, reference, or depend on anything inside `_build_plan/`.

Do not treat `_build_plan/` as long-living documentation for the codebase. The codebase will evolve past the assumptions and decisions captured here. Once the initial milestones are complete, this folder is expected to be deleted.
