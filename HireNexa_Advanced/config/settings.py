import sys
from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Load backend environment variables from .env file (preserving explicitly set process env vars)
load_dotenv(BASE_DIR / ".env", override=False)

try:
    from decouple import config as decouple_config
    def get_env(key, default=None, cast=None):
        if cast is not None:
            return decouple_config(key, default=default, cast=cast)
        return decouple_config(key, default=default)
except ImportError:
    def get_env(key, default=None, cast=None):
        val = os.environ.get(key, default)
        if cast is bool and isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        if cast is int and val is not None:
            try:
                return int(val)
            except ValueError:
                return default
        return val

DEBUG = str(get_env("DJANGO_DEBUG", "True")).lower() == "true"
ENVIRONMENT = str(get_env("ENVIRONMENT", "development" if DEBUG else "production")).strip().lower()
IS_PRODUCTION = (not DEBUG) or (ENVIRONMENT in ("production", "prod"))

# Platform Owner 2FA OTP requirement
# Default: False in development (Direct password sign-in after initial verification)
raw_owner_require_otp = get_env("OWNER_REQUIRE_OTP", None)
if any("test" in arg for arg in sys.argv):
    OWNER_REQUIRE_OTP = True
    UNIFIED_REQUIRE_OTP = True
elif raw_owner_require_otp is not None:
    OWNER_REQUIRE_OTP = str(raw_owner_require_otp).lower() in ("true", "1", "yes")
    UNIFIED_REQUIRE_OTP = str(get_env("UNIFIED_REQUIRE_OTP", "False")).lower() in ("true", "1", "yes")
else:
    OWNER_REQUIRE_OTP = False
    UNIFIED_REQUIRE_OTP = False


# SEC-01: Fail-closed secret key verification
SECRET_KEY = get_env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "hirenexa-enterprise-v2-dev-secret-key-production-ready"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable is required in production (DEBUG=False).")

# SEC-02: Strict allowed hosts governance
if DEBUG:
    ALLOWED_HOSTS = [h.strip() for h in str(get_env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,*")).split(",") if h.strip()]
else:
    raw_hosts = get_env("DJANGO_ALLOWED_HOSTS")
    if not raw_hosts or "*" in raw_hosts:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be explicitly defined and cannot contain wildcards in production.")
    ALLOWED_HOSTS = [h.strip() for h in raw_hosts.split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "core.apps.CoreConfig",
    "accounts",
    "recruitment",
    "ai_assistant.apps.AIAssistantConfig",
    "assessments.apps.AssessmentsConfig",
    "connect.apps.ConnectConfig",
]
# Only insert daphne for runserver command to avoid Twisted reactor hangs in CLI/test tasks on Windows
if "runserver" in sys.argv:
    INSTALLED_APPS.insert(0, "daphne")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.SessionTimeoutMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "accounts.context_processors.hirenexa_context",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ==============================================================================
# DJANGO CHANNELS & REAL-TIME WEBSOCKET CONFIGURATION
# ==============================================================================
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }

# ==============================================================================
# CENTRALIZED DATABASE CONFIGURATION
# PostgreSQL (Supabase) primary — SQLite fallback for offline dev
# ==============================================================================
import dj_database_url as _dj_db_url

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
POSTGRES_DB = os.environ.get("POSTGRES_DB") or os.environ.get("DB_NAME")

# Supabase / PgBouncer pooler requires CONN_MAX_AGE=0 (no persistent connections)
# to prevent FATAL: (EMAXCONNSESSION) max clients reached in session mode.
_IS_SUPABASE = bool(DATABASE_URL and "supabase" in (DATABASE_URL or ""))
_SUPABASE_IS_TRANSACTION_POOL = _IS_SUPABASE and ":6543/" in (DATABASE_URL or "")
_CONN_MAX_AGE = 0 if _IS_SUPABASE else int(get_env("CONN_MAX_AGE", 0))

_USE_SQLITE = (
    any("test" in arg for arg in sys.argv) and not os.environ.get("TEST_ON_POSTGRES")
) or str(get_env("USE_SQLITE", "0")).lower() in ("1", "true", "yes") or os.environ.get("USE_SQLITE") == "1"

if _USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
elif DATABASE_URL and ("postgres://" in DATABASE_URL or "postgresql://" in DATABASE_URL):
    # Normalize postgres:// → postgresql:// for psycopg2 compatibility
    _db_url_norm = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    DATABASES = {
        "default": _dj_db_url.parse(
            _db_url_norm,
            conn_max_age=_CONN_MAX_AGE,
            conn_health_checks=True,
        )
    }
    # Enforce SSL and resilient pooling options for Supabase / remote PostgreSQL connections
    if _IS_SUPABASE or "postgresql" in _db_url_norm:
        DATABASES["default"].setdefault("OPTIONS", {})
        DATABASES["default"]["OPTIONS"]["sslmode"] = "require"
        DATABASES["default"]["OPTIONS"]["connect_timeout"] = 15
        DATABASES["default"]["OPTIONS"]["keepalives"] = 1
        DATABASES["default"]["OPTIONS"]["keepalives_idle"] = 30
        DATABASES["default"]["OPTIONS"]["keepalives_interval"] = 10
        DATABASES["default"]["OPTIONS"]["keepalives_count"] = 5
elif POSTGRES_DB:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": POSTGRES_DB,
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": _CONN_MAX_AGE,
        }
    }
else:
    # Offline / local development fallback — SQLite
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Supabase API configuration (for REST API access, not Django ORM)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

AUTH_USER_MODEL = "accounts.User"

# Session Expiration & Security Settings
SESSION_COOKIE_AGE = 14400  # 4 hours timeout
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True

# Cache backend for rate limiting & sessions
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "hirenexa-rate-limit-cache",
    }
}

# SEC-05: Enterprise SSL/HTTPS and Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ==============================================================================
# EMAIL SERVICE & GMAIL SMTP CONFIGURATION
# ==============================================================================
EMAIL_BACKEND_MODE = str(get_env("EMAIL_BACKEND_MODE", "smtp")).strip().lower()

EMAIL_HOST = get_env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(get_env("EMAIL_PORT", 587))

# Support port 587 (TLS) and port 465 (SSL)
if EMAIL_PORT == 465:
    EMAIL_USE_SSL = True
    EMAIL_USE_TLS = False
else:
    EMAIL_USE_TLS = str(get_env("EMAIL_USE_TLS", "True")).lower() in ("true", "1", "yes")
    EMAIL_USE_SSL = str(get_env("EMAIL_USE_SSL", "False")).lower() in ("true", "1", "yes")

# Clean credentials (strip spaces, including 16-char app passwords formatted as "abcd efgh ijkl mnop")
EMAIL_HOST_USER = get_env("EMAIL_HOST_USER", "").strip()
raw_password = get_env("EMAIL_HOST_PASSWORD", "")
EMAIL_HOST_PASSWORD = raw_password.replace(" ", "").strip()

DEFAULT_FROM_EMAIL = get_env(
    "DEFAULT_FROM_EMAIL",
    f"HireNexa <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "HireNexa <noreply@hirenexa.com>"
)
EMAIL_TIMEOUT = int(get_env("EMAIL_TIMEOUT", 20))

# Resend API Service
RESEND_API_KEY = str(get_env("RESEND_API_KEY", "")).strip()
RESEND_FROM_EMAIL = str(get_env("RESEND_FROM_EMAIL", "onboarding@resend.dev")).strip()

IS_TESTING = any(arg in sys.argv for arg in ["test", "test_email", "check", "help", "migrate", "makemigrations"])

# Determine active EMAIL_BACKEND with console fallback in DEBUG
if EMAIL_BACKEND_MODE == "console":
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
elif EMAIL_BACKEND_MODE == "locmem" or (IS_TESTING and EMAIL_BACKEND_MODE != "smtp"):
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
elif EMAIL_BACKEND_MODE == "smtp":
    has_smtp_creds = bool(EMAIL_HOST_USER and EMAIL_HOST_PASSWORD)
    if has_smtp_creds:
        EMAIL_BACKEND = get_env("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    else:
        if DEBUG:
            # Fall back to console backend in DEBUG mode so OTPs are printed and visible locally
            EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
            print("[HIRENEXA INFO] SMTP credentials missing in .env. DEBUG=True -> Falling back to console.EmailBackend. "
                  "Verification emails will print to the terminal.")
        else:
            if not IS_TESTING:
                raise ImproperlyConfigured(
                    "Missing required SMTP environment variable(s): EMAIL_HOST_USER, EMAIL_HOST_PASSWORD in .env. "
                    "Please configure your Gmail address and 16-character App Password."
                )
            EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
else:
    EMAIL_BACKEND = get_env("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")

# ==============================================================================
# SMS PROVIDER & PLUGGABLE GATEWAY CONFIGURATION
# ==============================================================================
# Supported backends: console (DEBUG default), msg91, fast2sms, twilio, custom
SMS_BACKEND = str(get_env("SMS_BACKEND", get_env("SMS_PROVIDER", "console" if DEBUG else "twilio"))).strip().lower()
SMS_PROVIDER = SMS_BACKEND  # Backward compatibility

# Twilio
TWILIO_ACCOUNT_SID = get_env("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = get_env("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = get_env("TWILIO_FROM_NUMBER", "").strip()

# MSG91 (Indian DLT)
MSG91_AUTH_KEY = get_env("MSG91_AUTH_KEY", get_env("MSG91_AUTHKEY", "")).strip()
MSG91_FLOW_ID = get_env("MSG91_FLOW_ID", get_env("MSG91_TEMPLATE_ID", "")).strip()
MSG91_SENDER_ID = get_env("MSG91_SENDER_ID", "HIRNEX").strip()

# Fast2SMS (Indian SMS Gateway)
FAST2SMS_API_KEY = get_env("FAST2SMS_API_KEY", "").strip()

# Custom HTTP SMS Gateway
CUSTOM_SMS_GATEWAY_URL = get_env("CUSTOM_SMS_GATEWAY_URL", "").strip()

# ==============================================================================
# ENTERPRISE OTP CONFIGURATION (Cryptographic Email & Mobile OTP)
# ==============================================================================
OTP_EXPIRY_SECONDS = int(get_env("OTP_EXPIRY_SECONDS", 300))  # 5 minutes default
OTP_LENGTH = int(get_env("OTP_LENGTH", 6))
OTP_MAX_ATTEMPTS = int(get_env("OTP_MAX_ATTEMPTS", 5))
OTP_RESEND_COOLDOWN_SECONDS = int(get_env("OTP_RESEND_COOLDOWN_SECONDS", 60))
OTP_MAX_HOURLY_SENDS = int(get_env("OTP_MAX_HOURLY_SENDS", 5))



# ==============================================================================
# SECURITY & AUTHENTICATION (Argon2 Enterprise Password Hashing)
# ==============================================================================
AUTHENTICATION_BACKENDS = [
    "accounts.backends.MultiIdentifierModelBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Configurable Rate Limiting & Account Lockout
LOGIN_MAX_ATTEMPTS = int(get_env("LOGIN_MAX_ATTEMPTS", get_env("MAX_ATTEMPTS", 5)))
MAX_ATTEMPTS = LOGIN_MAX_ATTEMPTS
LOGIN_LOCKOUT_MINUTES = int(get_env("LOGIN_LOCKOUT_MINUTES", get_env("LOCKOUT_MINUTES", 1 if DEBUG else 15)))
LOCKOUT_MINUTES = LOGIN_LOCKOUT_MINUTES

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ==============================================================================
# REST FRAMEWORK & API
# ==============================================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_STORAGE_ROOT = BASE_DIR / "media" / "private_resumes"
PRIVATE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB

# ==============================================================================
# HIRENEXA AI ASSISTANT CONFIGURATION (Hybrid: OpenAI Primary, Ollama Fallback)
# ==============================================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

# Optional Google AI Studio (Gemini) Provider
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")).strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash").strip()

# Optional Groq Provider (Ultra-fast, OpenAI-compatible)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

# Optional Anthropic Claude Provider
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", os.environ.get("OLLAMA_HOST", "http://localhost:11434")).strip()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2").strip()

AI_PRIMARY_PROVIDER = os.environ.get("AI_PRIMARY_PROVIDER", "openai").lower()
AI_FALLBACK_PROVIDER = os.environ.get("AI_FALLBACK_PROVIDER", "ollama").lower()
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "4096"))
AI_TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0.7"))
AI_REQUEST_TIMEOUT = float(os.environ.get("AI_REQUEST_TIMEOUT", "30.0"))
AI_RATE_LIMIT_PER_MINUTE = int(os.environ.get("AI_RATE_LIMIT_PER_MINUTE", "30"))

AI_UPLOAD_DIR = BASE_DIR / "media" / "ai_attachments"
AI_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}:{lineno} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "accounts.security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "accounts.email": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "accounts.sms": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ==============================================================================
# ENTERPRISE ZOOM VIDEO INTERVIEW CONFIGURATION
# ==============================================================================
ZOOM_ACCOUNT_ID = str(get_env("ZOOM_ACCOUNT_ID", "")).strip()
ZOOM_CLIENT_ID = str(get_env("ZOOM_CLIENT_ID", "")).strip()
ZOOM_CLIENT_SECRET = str(get_env("ZOOM_CLIENT_SECRET", "")).strip()
ZOOM_WEBHOOK_SECRET = str(get_env("ZOOM_WEBHOOK_SECRET", "")).strip()
ZOOM_API_BASE_URL = "https://api.zoom.us/v2"
ZOOM_OAUTH_TOKEN_URL = "https://zoom.us/oauth/token"

