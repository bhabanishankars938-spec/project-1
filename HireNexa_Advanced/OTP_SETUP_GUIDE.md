# HireNexa OTP Verification & Messaging Configuration Guide

This guide details the setup for Email and SMS OTP verification in HireNexa, explaining how to configure Gmail SMTP, SMS gateways (Twilio, MSG91), and local development fallback modes.

---

## 1. Quick Summary of Environment Variables (`.env`)

```ini
# Core
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=your-production-secret-key
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# ==============================================================================
# Email OTP (Gmail SMTP)
# ==============================================================================
EMAIL_BACKEND_MODE=smtp          # Options: 'smtp' (production/live) or 'console' (local test)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your-email@gmail.com
# 16-character Google App Password (not your personal account password)
EMAIL_HOST_PASSWORD=abcdefghijklmnop
DEFAULT_FROM_EMAIL="HireNexa <your-email@gmail.com>"
EMAIL_TIMEOUT=20

# ==============================================================================
# SMS OTP Gateway
# ==============================================================================
# Options: 'mock' (DEBUG console output), 'twilio', or 'msg91'
SMS_PROVIDER=mock

# Twilio (Global SMS)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1234567890

# MSG91 (Indian DLT SMS)
MSG91_AUTH_KEY=your_msg91_auth_key
MSG91_FLOW_ID=your_dlt_template_flow_id
MSG91_SENDER_ID=HIRNEX

# Custom SMS Gateway (optional)
CUSTOM_SMS_GATEWAY_URL=
```

---

## 2. Gmail SMTP Setup with 16-Character App Password

Google requires an **App Password** when sending emails through `smtp.gmail.com:587`. Regular account passwords will be rejected with an `SMTPAuthenticationError (535)`.

### Step-by-Step Instructions:
1. Log into your Google Account.
2. Go to **Google Account Security**: https://myaccount.google.com/security
3. Ensure **2-Step Verification** is turned **ON**.
4. Search for or navigate to **App passwords**: https://myaccount.google.com/apppasswords
5. Enter an app name (e.g. `HireNexa`).
6. Click **Create**. Google will display a 16-character passcode like `abcd efgh ijkl mnop`.
7. Copy this string and paste it into `.env` as `EMAIL_HOST_PASSWORD`:
   ```ini
   EMAIL_HOST_USER=myaccount@gmail.com
   EMAIL_HOST_PASSWORD=abcdefghijklmnop
   ```
   *(Note: HireNexa automatically strips spaces from `EMAIL_HOST_PASSWORD`)*.

---

## 3. Local Development Fallback Behavior (`DEBUG=True`)

- **Email Fallback**: If `EMAIL_HOST_USER` or `EMAIL_HOST_PASSWORD` is blank while `DEBUG=True`, HireNexa automatically falls back to Django's `console.EmailBackend`. Verification emails and OTP codes will be printed directly in your terminal rather than failing silently.
- **SMS Mock Provider**: When `SMS_PROVIDER=mock` (default in `DEBUG=True`), SMS codes are printed to the console in a high-visibility terminal banner with a 10-minute validity timestamp.

---

## 4. Verification Rules (OR Logic)

- **Account Activation**: A registered user activates their account and is logged in when **EITHER** email OTP **OR** mobile SMS OTP is successfully verified.
- **Optional Contact Method**: The unverified contact method remains optional and can be verified at any later time from the profile settings.
- **Security Protections**:
  - 6-digit cryptographically secure code (`secrets.SystemRandom`)
  - Stored hashed using HMAC-SHA256 (`django.conf.settings.SECRET_KEY`)
  - 10-minute expiry window
  - Max 5 verification attempts per code before challenge lockout
  - 60-second cooldown timer between resend requests
  - IP and recipient rate limiting (max 5 requests per hour)
