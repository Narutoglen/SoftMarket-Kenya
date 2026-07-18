# Contributing to SoftMarket Kenya

Thanks for helping improve SoftMarket KE. This guide covers local setup and the checks a
change must pass before it's opened as a PR.

## Local setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      Unix:  source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

A basic run needs **no environment variables**: with `DJANGO_DEBUG=True` (the local default)
and no `DATABASE_URL`, the app uses `db.sqlite3` and the console email backend — no external
services required. `.env.example` documents the variables for production (Vercel) and for
exercising integrations (M-Pesa, Cloudinary, real SMTP). Note the app reads real environment
variables directly — there is no dotenv auto-loader — so `export` them in your shell (or add
your own loader) rather than expecting a `.env` file to be picked up automatically.

## The gate (run before every PR)

```bash
python manage.py check                              # system checks
python manage.py makemigrations --check --dry-run   # no unaccounted model changes
python manage.py test                               # full test suite
```

These three must pass, and every bug fix or behavioural change needs a regression test.

Linting/formatting is configured in `pyproject.toml` (ruff + black) and is **newly
introduced**, so the existing tree still has pre-existing drift. Until a maintainer runs a
one-off repo-wide `ruff check --fix . && ruff format .`, lint your own changes rather than
reformatting untouched files:

```bash
pip install ruff black          # dev tools, intentionally not in requirements.txt
ruff check <files you changed>
ruff format --check <files you changed>   # or: black --check <files>
```

## PR conventions

- Keep PRs small and single-purpose so they can be reviewed and merged independently.
- Don't reformat files you didn't otherwise touch.
- Never commit secrets, `.env`, `db.sqlite3`, or `.venv/`.
- Migrations are code — commit the generated migration file alongside the model change.

## Project layout

- `marketplace/` — public site, project-request & developer-application intake, M-Pesa Daraja
  payments, notifications (email/SMS), analytics dashboard, CSV/XLSX export.
- `crm/` — white-label multi-tenant CRM core (Tenant → Account/Contact → Activity/Lead/Opportunity, Kanban).
- `softmarket/` — Django project settings/urls/wsgi (Vercel entrypoint).
- `_build_plan/` — historical PRD/milestone prompts; **not** load-bearing, safe to ignore/delete.
