# HireNexa V3 Enterprise SaaS – Production Deployment Guide

## Vercel Deployment

Set the Vercel project Root Directory to `HireNexa_Advanced`. Configure these
environment variables in the Vercel project before deploying:

- `DJANGO_SECRET_KEY`: a unique, strong production secret.
- `DJANGO_DEBUG`: `False`.
- `ENVIRONMENT`: `production`.
- `DJANGO_ALLOWED_HOSTS`: the exact Vercel deployment hostname and any custom
  hostnames, separated by commas (do not use `*`).
- `DATABASE_URL`: a managed PostgreSQL connection string; Vercel's function
  filesystem is temporary, so SQLite is not suitable for persistent data.
- Email delivery settings: provide `EMAIL_HOST_USER` and
  `EMAIL_HOST_PASSWORD` when using the default SMTP backend.

The optional transformer packages are kept in `requirements-ml.txt` because
they pull in large ML dependencies unsuitable for Vercel's serverless function
size limits. The application uses its built-in lexical similarity fallback
when those packages are not installed. For a non-serverless deployment that
needs transformer-based matching, install both requirements files.

## 1. System Overview & Architecture
HireNexa is an enterprise-grade multi-tenant AI recruitment SaaS application built with Python 3.12+, Django 6.1, PostgreSQL 16, and optional Sentence-Transformers NLP.

```
       [ Internet Users & Corporate Recruiters ]
                         │
                    HTTPS (443)
                         ▼
                [ Nginx Reverse Proxy ]
               (SSL Termination / Static)
                         │
                    UNIX Socket
                         ▼
              [ Gunicorn WSGI Workers ]
                         │
       ┌─────────────────┴─────────────────┐
       ▼                                   ▼
 [ Django 5 Core Application ]   [ Private Object Storage ]
 (5-Tier RBAC & 7 AI Agents)    (Resumes & Audit Records)
       │
       ▼
 [ PostgreSQL 16 Multi-Tenant DB ]
```

---

## 2. Environment Variables & Configuration
Create a secure production environment file at `/opt/hirenexa/.env` (or in container secrets):

```bash
# Security & Debug
DEBUG=False
SECRET_KEY=generate-a-strong-random-64-char-string-in-production
ALLOWED_HOSTS=hirenexa.com,www.hirenexa.com,app.hirenexa.com

# Database Connection (PostgreSQL Production)
DATABASE_URL=postgresql://hirenexa_prod_user:SuperSecureProdPassword123!@127.0.0.1:5432/hirenexa_enterprise_db

# Password Hashing
PASSWORD_HASHING_ALGORITHM=argon2

# Storage Configuration
PRIVATE_MEDIA_ROOT=/opt/hirenexa/private_media
STATIC_ROOT=/opt/hirenexa/staticfiles

# Payment Gateway (Razorpay / Stripe)
PAYMENT_GATEWAY_PROVIDER=RAZORPAY
RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=live_secret_xxxxxxxxxxxx

# AI Models & NLP Cache
TRANSFORMERS_CACHE=/opt/hirenexa/.cache/huggingface
```

---

## 3. Server Provisioning & Dependencies (Ubuntu 22.04 / 24.04 LTS)

### A. System Packages Installation
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib libpq-dev \
    nginx git curl build-essential libmagic1
```

### B. PostgreSQL Database Setup
```bash
sudo -u postgres psql
```
```sql
CREATE DATABASE hirenexa_enterprise_db;
CREATE USER hirenexa_prod_user WITH PASSWORD 'SuperSecureProdPassword123!';
ALTER ROLE hirenexa_prod_user SET client_encoding TO 'utf8';
ALTER ROLE hirenexa_prod_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE hirenexa_prod_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE hirenexa_enterprise_db TO hirenexa_prod_user;
\q
```

---

## 4. Application Setup & Migrations

```bash
# Clone and setup virtual environment
cd /opt
sudo git clone <repo_url> hirenexa
sudo chown -R ubuntu:ubuntu hirenexa
cd /opt/hirenexa/HireNexa_Advanced

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# Run Database Migrations
python manage.py migrate

# Collect Static Assets
python manage.py collectstatic --noinput

# Initialize Protected Platform Owner Account
python manage.py create_platform_owner --username admin_owner --email owner@hirenexa.com --password "SecureEnterpriseOwner2026!"
```

---

## 5. Systemd Service Configuration (`/etc/systemd/system/hirenexa.service`)

```ini
[Unit]
Description=HireNexa Enterprise Gunicorn Application Service
After=network.target postgresql.service

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/opt/hirenexa/HireNexa_Advanced
EnvironmentFile=/opt/hirenexa/.env
ExecStart=/opt/hirenexa/HireNexa_Advanced/venv/bin/gunicorn \
          --workers 4 \
          --worker-class gthread \
          --threads 4 \
          --timeout 120 \
          --bind unix:/run/hirenexa.sock \
          config.wsgi:application

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hirenexa
sudo systemctl start hirenexa
sudo systemctl status hirenexa
```

---

## 6. Nginx Reverse Proxy Configuration (`/etc/nginx/sites-available/hirenexa`)

```nginx
server {
    listen 80;
    server_name hirenexa.com www.hirenexa.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name hirenexa.com www.hirenexa.com;

    ssl_certificate /etc/letsencrypt/live/hirenexa.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hirenexa.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    # Static Assets
    location /static/ {
        alias /opt/hirenexa/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }

    # Protected Resumes (Private Storage)
    location /media/private_resumes/ {
        internal;
        alias /opt/hirenexa/private_media/private_resumes/;
    }

    # Application Proxy
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/hirenexa.sock;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
}
```

Enable site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/hirenexa /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 7. Zero-Downtime Deployment Runbook
For updates and new releases:
1. `git pull origin main`
2. `source venv/bin/activate`
3. `pip install -r requirements.txt`
4. `python manage.py migrate --noinput`
5. `python manage.py collectstatic --noinput`
6. `sudo systemctl reload hirenexa`
7. Check health: `curl -I https://hirenexa.com`
