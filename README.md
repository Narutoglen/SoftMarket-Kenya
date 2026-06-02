# SoftMarket Kenya

Backend-powered Django website for a Kenyan software marketplace.

## Files

- `templates/marketplace/home.html` - Django homepage template
- `static/marketplace/styles.css` - responsive styling
- `static/marketplace/script.js` - mobile navigation, UTM capture, WhatsApp, and form backup
- `marketplace/models.py` - project requests, developers, assignments, payments, and notifications
- `marketplace/admin.py` - Django admin configuration and actions

## Preview

Run the Django development server:

```powershell
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
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

## Forms And Notifications

The public project request form saves directly into Django. The backend also supports developer application submissions when a form posts `form-name=developer-application`. Email uses Django's console backend by default. Configure these environment variables for production notifications:

```text
ADMIN_NOTIFICATION_EMAILS=you@example.com
DEFAULT_FROM_EMAIL=SoftMarket Kenya <hello@example.com>
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
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
