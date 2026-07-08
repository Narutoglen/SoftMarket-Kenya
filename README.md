# SoftMarket Kenya

Backend-powered Django website for a Kenyan software marketplace.

## Files

- `templates/marketplace/home.html` - Django homepage template
- `static/marketplace/styles.css` - responsive styling
- `static/marketplace/script.js` - mobile navigation, UTM capture, WhatsApp, and form backup
- `marketplace/models.py` - project requests, developers, assignments, payments, and notifications
- `marketplace/admin.py` - Django admin configuration and actions

## Preview

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the Django development server:

```powershell
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

By default, local development uses `db.sqlite3` when `DJANGO_DEBUG=True`.
To use Postgres locally instead, create a database named `softmarket_kenya` and set:

```powershell
$env:DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/softmarket_kenya"
```

Then open:

```text
http://127.0.0.1:8000/
```

## Configure WhatsApp

Update `BUSINESS_WHATSAPP_NUMBER` in `static/marketplace/script.js` with the real business WhatsApp number in international format.

The current configured number is `254716343561`.

## Admin

Create an admin user:

```powershell
python manage.py createsuperuser
```

Then open:

```text
http://127.0.0.1:8000/admin/
```

Analytics and exports are available at:

```text
http://127.0.0.1:8000/dashboard/analytics/
http://127.0.0.1:8000/dashboard/export/project-requests.csv
http://127.0.0.1:8000/dashboard/export/project-requests.xlsx
```

## Deploy To Vercel

This project is configured for Vercel using `vercel.json` (Python runtime, gunicorn WSGI).

1. Push the repository to GitHub.
2. In Vercel, import the repo and deploy. Vercel auto-detects the Python runtime from
   `vercel.json` and runs `python manage.py collectstatic --no-input` at build time.
3. Vercel provisions a `*.vercel.app` domain automatically; `ALLOWED_HOSTS` and
   `CSRF_TRUSTED_ORIGINS` pick it up from the `VERCEL_URL` env var (no manual host config needed).
4. Add a Postgres database from an external provider (Vercel has no built-in Postgres). Recommended:
   Neon or Supabase. Set its connection string as `DATABASE_URL` in Vercel project env.
5. After the first deploy, run migrations and create an admin user via the Vercel CLI / terminal:

```bash
vercel env pull .env.local        # fetch env vars locally
python manage.py migrate
python manage.py createsuperuser
```

Build/start behavior:

```bash
# build command (runs automatically on Vercel)
python manage.py collectstatic --no-input

# runtime: gunicorn wsgi via the @vercel/python function in vercel.json
```

Required production environment variables:

```text
DJANGO_SECRET_KEY=generate-a-long-random-string
DJANGO_DEBUG=False
DATABASE_URL=postgresql://user:pass@your-neon-or-supabase-host/dbname
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com
```

`VERCEL_URL` is injected by Vercel automatically (do not set it yourself).

If production logs mention missing database tables, the app is missing `DATABASE_URL` or
migrations did not run. Set `DATABASE_URL` to your external Postgres connection string, then
redeploy so `migrate` runs during the build before the app starts.

Optional security hardening after the final domain is confirmed:

```text
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
```

Only enable those HSTS options when every subdomain should be HTTPS-only.

## Forms And Notifications

The public project request form saves directly into Django. The backend also supports developer application submissions when a form posts `form-name=developer-application`. Email uses Django's console backend by default. Configure these environment variables for production notifications:

```text
ADMIN_NOTIFICATION_EMAILS=you@example.com
DEFAULT_FROM_EMAIL=SoftMarket Kenya <hello@example.com>
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True
```

For SMS, set:

```text
SOFTMARKET_SMS_WEBHOOK_URL=https://your-sms-provider-endpoint
SOFTMARKET_SMS_WEBHOOK_TOKEN=optional-token
```

## M-Pesa Daraja

Set these before using real STK Push payments:

```text
MPESA_ENVIRONMENT=sandbox
MPESA_CONSUMER_KEY=...
MPESA_CONSUMER_SECRET=...
MPESA_BUSINESS_SHORTCODE=...
MPESA_PASSKEY=...
MPESA_CALLBACK_URL=https://your-domain.com/payments/mpesa/callback/
```

Booking deposit STK pushes can be triggered from the Django admin action on selected project requests.
