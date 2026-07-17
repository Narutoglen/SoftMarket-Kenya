# White-Label Retail CRM

> **About these build-plan files:** Everything in `_build_plan/` (this PRD and the per-milestone folders) is a **temporary documentation and guidance artifact** for the initial build-out of this codebase. These files are not functional — no code, configuration, runtime logic, tests, or deployment process should import, read, reference, or depend on anything in `_build_plan/`. Once the initial milestones are built and shipped, the entire `_build_plan/` folder is expected to be deleted from the codebase. Do not treat it as long-living documentation.

## What we're building

A single reusable CRM core that ships configured per retail client. SoftMarket KE is tenant #1; the next supermarket is a new `Tenant` row plus branding/config — not a code fork. It follows a contact-centric 360° model where Contact is the hub and Account, Activity, Lead, and Opportunity all relate to it. Retail retention economics (catch churn early, nurture loyalty, clean vendor relations) drive the design, with Kenyan-market hooks (M-Pesa, WhatsApp, eTIMS, offline sync) designed in from v1. Stack: Django + PostgreSQL/Supabase, Tailwind, HTMX, deployed on Vercel. The build is broken into 6 dependency-ordered milestones; each milestone is a self-contained agent session that ends with a `milestone-log.md`.

---

### What the app does

- **Contact hub (360° view)** — every customer/vendor in one place with a timeline of every call, email, note, and deal.
- **Multi-tenant white-label** — one codebase serves many clients as isolated instances, each with its own branding and pipeline.
- **Lead capture + BANT scoring** — public web form turns strangers into scored leads (hot/warm/cold) and routes them by territory.
- **Kanban opportunity pipeline** — drag deals across stages, see per-stage value totals and a weighted forecast.
- **Activity & follow-ups** — timestamped log plus a to-do list of next actions linked back to each deal.
- **Retention & churn signals** — lifecycle tracking flags customers with no recent activity so you re-engage before they leave.
- **Per-tenant configuration** — each client configures its own pipeline stages and key fields, no code change.
- **Integration hooks** — M-Pesa, WhatsApp Business, eTIMS export, and offline sync wire in as the build progresses.

---

### Already provided by the existing SoftMarket codebase

- Tenant + `InstanceScopedModel` (multi-tenant base)
- Contact, Account, Activity, Lead, Opportunity models
- BANT scoring service on Lead
- Django JSON API at `/api/*`
- Vercel deployment config

---

### Out of scope

- **Team seats / RBAC** — single owner string per record in v1; full multi-user when a client needs it.
- **Email-blast marketing** — only the triggered lead auto-responder ships in v1.
- **Inventory / POS module** — the CRM is not the store; expose hooks only.
- **Custom report builder** — ship a fixed set of preset retail reports instead.
- **Bi-directional accounting** — eTIMS export only, no live ledger sync.
- **Native mobile apps** — responsive web only in v1.
- **In-product AI features** — the build uses AI; the shipped CRM does not (future scope).

---

### External integrations

- **M-Pesa (Buy Goods)** — record payments against deals/contacts. Creds: Till/Paybill, Daraja consumer key+secret, callback URL.
- **WhatsApp Business API** — send/log messages as activities. Creds: Meta WABA ID, per-tenant token, phone number ID.
- **eTIMS export** — KRA-compliant export. Creds: taxpayer PIN, eTIMS device/branch ID.
- **Offline sync** — field reps keep working without signal; no external creds (client-side queue + conflict strategy).

---

### Data model

- **Tenant** — slug, name, brand colors/logo, default lead owner, active. Parent of every other entity.
- **Account** — name, industry, website, phone, billing address, notes. Has many Contacts and Opportunities.
- **Contact** — name/email/phone, date of birth, personal notes, lifecycle (subscriber→lead→customer→churned), territory. The hub: has Activities, Leads, Opportunities.
- **Activity** — type (call/email/meeting/note/task), subject, notes, due at, done. Belongs to one Contact.
- **Lead** — source, message, BANT answers (1–3 each), rating (hot/warm/cold), owner, auto-responded. Converts into a Contact.
- **Opportunity** — name, amount (KSh), stage, probability, close date, owner. Belongs to one Contact and one Account.
- **TenantStage (new in v1)** — tenant, name, order. Makes each client's pipeline configurable (the white-label requirement).

---

## Milestone 1 — Tenant + Contact/Account CRUD

Lay the white-label foundation and the two core entities every later feature depends on.

### What gets built

- Tenant model + branding hooks (colors, logo)
- Contact list, detail, create/edit/delete
- Account (vendor) list, detail, CRUD
- 360° shell that will later show the timeline

### What milestone 1 explicitly does NOT include

- Leads or deals (later milestones)
- Kanban board
- Automation/auto-responder

### Done when

Logged-in user can create contacts and accounts, open a contact, and see tenant branding applied.

---

## Milestone 2 — Activity log + 360° timeline

Attach the interaction history to each contact so the hub view comes alive.

### What gets built

- Log calls/emails/meetings/notes/tasks
- Timestamped timeline on the contact page
- Mark tasks done

### What milestone 2 explicitly does NOT include

- Follow-up reminders/notifications (M5)
- Bulk import UI

### Done when

Opening any contact shows every interaction in order, newest first.

---

## Milestone 3 — Lead capture + BANT scoring

Turn the public web form into scored, routed leads without manual triage.

### What gets built

- Public web-intake form
- Auto BANT score → hot/warm/cold
- Territory auto-assign + auto-responder email

### What milestone 3 explicitly does NOT include

- Lead de-dupe/merge
- Manual BANT entry UI

### Done when

Submitting the form creates a rated lead owned by the right rep with an auto-reply sent.

---

## Milestone 4 — Opportunity pipeline (Kanban)

Give deals a board with drag-and-drop and a forecast.

### What gets built

- Board + list views
- Drag deals across stages (persisted)
- Drag to reorder within a column
- Per-stage value totals + weighted forecast
- Associate multiple contacts with a deal

### What milestone 4 explicitly does NOT include

- Per-deal probability editing UI
- Custom fields per deal

### Done when

User can drag a deal to Won and watch the stage total and forecast update.

---

## Milestone 5 — Follow-ups + churn detection

Make sure nothing falls through the cracks and at-risk customers surface early.

### What gets built

- To-do list of next actions with due dates
- Check-off linking back to the deal
- Lifecycle transitions
- Churn flag on customers with no activity in N days

### What milestone 5 explicitly does NOT include

- Push/email reminders (in-app only v1)
- Predictive/ML churn

### Done when

A rep sees today's follow-ups and a list of customers who've gone quiet.

---

## Milestone 6 — White-label config + integration hooks

Make the core resellable and wire in the Kenyan-market integrations.

### What gets built

- Per-tenant pipeline stage configuration UI
- Branding UI (colors/logo)
- M-Pesa, WhatsApp, eTIMS, offline-sync interfaces + queues

### What milestone 6 explicitly does NOT include

- Live third-party calls for every channel (contracts wired, real creds per tenant later)
- Full SSO/multi-user

### Done when

A second tenant (new row + stages/branding) renders isolated, branded, and integration-ready.

---

