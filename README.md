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

## Deploy To Render

This project is configured for Render using `render.yaml`.

1. Push the repository to GitHub.
2. In Render, create a new Blueprint from this repo.
3. Render will create:
   - a Django web service named `softmarket-kenya`
   - a Postgres database named `softmarket-kenya-db`
4. Fill in the secret values Render prompts for, especially Cloudinary and M-Pesa credentials.
5. After the first deploy, open Render Shell and create a production admin user:

```bash
python manage.py createsuperuser
```

Render commands are:

```bash
pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate
gunicorn softmarket.wsgi:application
```

The default Blueprint uses Render free plans, so migrations run in the build command instead of `preDeployCommand`.

Required production environment variables:

```text
DJANGO_SECRET_KEY=generated-by-render
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.onrender.com,your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.onrender.com,https://your-domain.com
DATABASE_URL=provided-by-render-postgres
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

If production logs mention missing database tables, the web service is probably missing `DATABASE_URL` or migrations did not run. Deploy from the Blueprint in `render.yaml`, or create a Render Postgres database manually and set the web service `DATABASE_URL` to the database internal connection string. Then redeploy so `python manage.py migrate` runs during the build before the app starts.

Optional security hardening after the final domain is confirmed:

```text
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
```

Only enable those HSTS options when every subdomain should be HTTPS-only.

The default Blueprint uses Render free plans for previewing. Upgrade before serious production use because free Render Postgres databases expire and do not include backups.

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
