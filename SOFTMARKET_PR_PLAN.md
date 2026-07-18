# SoftMarket-Kenya — Contribution Plan (separate job, parallel to the DEV audit sweep)

Repo: `Narutoglen/SoftMarket-Kenya` (NOT owned by us — TatiShayo has **write/collaborator** access).
Strategy: **multiple small, independent PRs off `origin/main`** so the owner can accept/reject each one. Never push to `main`. Never force-push. No `.github/workflows` (token lacks `workflow` scope — deliver CI as a doc snippet in the PR body, marked NEEDS HUMAN).

Stack: Django 5.2, DRF, Postgres (dj-database-url), Cloudinary, whitenoise, django-htmx, django-cors-headers. Python 3.13. Vercel (gunicorn wsgi). Apps: `marketplace` (project requests, developers, assignments, M-Pesa Daraja payments, notifications, CSV/XLSX export, analytics dashboard), `crm` (white-label multi-tenant: Tenant → Account/Contact → Activity/Lead/Opportunity, Kanban).

## PR branches
- `pr/security-hardening` — settings secrets/DEBUG/headers/HSTS/CORS; M-Pesa callback auth + amount/state validation + idempotency guard; CSV/XLSX formula-injection sanitisation on exports; CRM tenant-isolation (IDOR) enforcement; form input validation.
- `pr/reliability` — payment idempotency & atomic mutations, DB constraints/unique-together, transaction.atomic, robust error handling on external calls (M-Pesa token/STK, SMS webhook, email).
- `pr/performance` — N+1 fixes (select_related/prefetch_related), DB indexes, pagination on list/API/export, query-count regression assertions.
- `pr/tests-and-dx` — expand tests (payments callback, tenant isolation, export sanitisation, forms), `.env.example`, ruff/black config, CONTRIBUTING notes. CI workflow as doc snippet only.

## Gate per PR (must pass before push)
`python manage.py check`; `python manage.py makemigrations --check --dry-run` (no unaccounted model changes); `python manage.py test`; each new fix backed by a regression test where feasible.

## Status
- [x] REVIEW.md written (all-aspects findings, severity-ranked)
- [x] PR1 security pushed + opened — #1 `pr/security-hardening`
- [x] PR2 reliability pushed + opened — #2 `pr/reliability`
- [x] PR3 performance pushed + opened — #3 `pr/performance`
- [x] PR4 tests/dx pushed + opened — #4 `pr/tests-and-dx`
