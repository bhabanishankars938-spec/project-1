"""
HireNexa SQLAlchemy Database Layer
===================================
Provides raw SQLAlchemy connectivity alongside Django ORM for:
  - Analytics aggregations on the owner dashboard
  - Audit log inspection
  - Cross-table queries too complex for Django ORM

Connection strategy:
  • Supabase / PgBouncer transaction-pooler (port 6543) → NullPool (no persistent connections)
  • Supabase / PgBouncer session-pooler (port 5432)     → QueuePool (default)
  • SQLite (local dev fallback)                         → StaticPool
"""

import os
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
    Numeric,
    ForeignKey,
    JSON,
    func,
    select,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.pool import NullPool, StaticPool

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
# Ensure .env is loaded for standalone SQLAlchemy usage
if (BASE_DIR / ".env").exists():
    load_dotenv(BASE_DIR / ".env", override=False)
elif (BASE_DIR.parent / ".env").exists():
    load_dotenv(BASE_DIR.parent / ".env", override=False)

DEFAULT_SQLITE_PATH = BASE_DIR / "db.sqlite3"

Base = declarative_base()


def _utcnow():
    """Timezone-aware UTC datetime. Replaces deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


def get_database_url() -> str:
    """
    Returns the database URL for SQLAlchemy.

    Priority order:
      1. Django active database connection (if Django configured and using SQLite)
      2. DATABASE_URL  (full connection string — preferred for Supabase)
      3. POSTGRES_URL  (alias)
      4. POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_HOST / POSTGRES_PORT
      5. SQLite fallback (portable local development)

    For PostgreSQL, we explicitly use the +psycopg2 dialect driver to ensure
    compatibility across both SQLAlchemy 1.x and 2.x without requiring psycopg3.
    """
    # 1. Align with Django's configured database when running under Django
    try:
        from django.conf import settings as django_settings
        if getattr(django_settings, "configured", False):
            default_db = getattr(django_settings, "DATABASES", {}).get("default", {})
            engine_backend = default_db.get("ENGINE", "")
            if "sqlite" in engine_backend:
                db_name = default_db.get("NAME")
                if db_name:
                    db_str = str(db_name).replace("\\", "/")
                    if db_str.startswith("file:"):
                        if "uri=true" not in db_str.lower():
                            sep = "&" if "?" in db_str else "?"
                            db_str = f"{db_str}{sep}uri=true"
                        return f"sqlite:///{db_str}"
                    elif db_str != ":memory:":
                        return f"sqlite:///{db_str}"
                sqlite_path = str(DEFAULT_SQLITE_PATH).replace("\\", "/")
                return f"sqlite:///{sqlite_path}"
    except Exception:
        pass

    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if url:
        # Normalize postgres:// → postgresql:// for SQLAlchemy / psycopg2
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # Explicitly use psycopg2 driver (postgresql+psycopg2://)
        # SQLAlchemy 2.x defaults to psycopg3 if psycopg is installed;
        # pin to psycopg2 for stability since that's what Django uses too.
        if url.startswith("postgresql://") and "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    # Check individual PostgreSQL environment variables
    pg_db = os.environ.get("POSTGRES_DB")
    pg_user = os.environ.get("POSTGRES_USER")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "")
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")

    if pg_db and pg_user:
        auth = f"{pg_user}:{pg_pass}@" if pg_pass else f"{pg_user}@"
        return f"postgresql+psycopg2://{auth}{pg_host}:{pg_port}/{pg_db}"

    # Offline local development fallback
    sqlite_path = str(DEFAULT_SQLITE_PATH).replace("\\", "/")
    return f"sqlite:///{sqlite_path}"


def _build_engine_kwargs(db_url: str) -> dict:
    """
    Returns SQLAlchemy engine kwargs tuned for the connection type.

    Supabase PgBouncer transaction-mode (port 6543):
      → NullPool: psycopg2 must NOT hold connections across requests.

    Supabase session-mode / direct Postgres (port 5432):
      → Default QueuePool with health checks.

    SQLite:
      → StaticPool with same-thread disabled (for Django dev server threads).
    """
    is_sqlite = db_url.startswith("sqlite")
    is_pgbouncer_transaction = "supabase" in db_url and ":6543/" in db_url

    kwargs: dict = {
        "pool_pre_ping": True,
        "future": True,
    }

    if is_sqlite:
        kwargs["poolclass"] = StaticPool
        connect_args = {"check_same_thread": False}
        if "file:" in db_url or "uri=true" in db_url.lower():
            connect_args["uri"] = True
        kwargs["connect_args"] = connect_args
    elif is_pgbouncer_transaction:
        # Transaction-mode PgBouncer: no persistent connections allowed
        kwargs["poolclass"] = NullPool
        logger.info("[SQLAlchemy] Using NullPool for Supabase PgBouncer transaction-mode pooler.")
    else:
        # Session-mode pooler or direct Postgres connection
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_timeout"] = 30
        kwargs["pool_recycle"] = 1800
        logger.info("[SQLAlchemy] Using QueuePool for Supabase session-mode / direct PostgreSQL.")

    return kwargs


_engine = None
_SessionFactory = None
_current_db_url = None


def get_engine():
    """Returns the singleton SQLAlchemy engine, creating it on first call or URL change."""
    global _engine, _SessionFactory, _current_db_url
    db_url = get_database_url()
    if _engine is None or _current_db_url != db_url:
        if _engine is not None:
            try:
                _engine.dispose()
            except Exception:
                pass
        engine_kwargs = _build_engine_kwargs(db_url)
        _engine = create_engine(db_url, **engine_kwargs)
        _SessionFactory = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        )
        _current_db_url = db_url
        logger.info(
            "[SQLAlchemy] Engine created. Dialect: %s",
            _engine.dialect.name.upper()
        )
    return _engine


@contextmanager
def get_sqlalchemy_session():
    """Thread-safe context manager for SQLAlchemy sessions."""
    get_engine()
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _SessionFactory.remove()


# ==============================================================================
# SQLAlchemy Models — mirrors Django ORM schema (read/analytics only)
# ==============================================================================

class UserSQLA(Base):
    __tablename__ = "accounts_user"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(150), unique=True, nullable=False)
    email = Column(String(254), nullable=False)
    password = Column(String(128), nullable=False)
    role = Column(String(20), default="CANDIDATE", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_staff = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    date_joined = Column(DateTime(timezone=True), default=_utcnow)
    last_login = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<UserSQLA(username='{self.username}', role='{self.role}')>"


class AuditLogSQLA(Base):
    __tablename__ = "accounts_auditlog"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("accounts_user.id"), nullable=True)
    action = Column(String(100), nullable=False)
    ip_address = Column(String(45), default="")
    user_agent = Column(Text, default="")
    details = Column(JSON, default=dict)
    timestamp = Column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self):
        return f"<AuditLogSQLA(action='{self.action}', time='{self.timestamp}')>"


class PlatformSettingSQLA(Base):
    __tablename__ = "accounts_platformsetting"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(String(255), default="")
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<PlatformSettingSQLA(key='{self.key}')>"


class FreelancerProfileSQLA(Base):
    __tablename__ = "recruitment_freelancerprofile"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("accounts_user.id"), unique=True, nullable=False)
    full_name = Column(String(120), default="")
    headline = Column(String(160), default="")
    hourly_rate = Column(Numeric(10, 2), default=0.00)
    experience_years = Column(Integer, default=0)
    skills = Column(String(500), default="")
    portfolio_url = Column(String(200), default="")
    availability = Column(String(30), default="AVAILABLE")
    updated_at = Column(DateTime(timezone=True), default=_utcnow)


class ProjectSQLA(Base):
    __tablename__ = "recruitment_project"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    client_id = Column(BigInteger, ForeignKey("accounts_user.id"), nullable=False)
    title = Column(String(180), nullable=False)
    company_name = Column(String(160), default="")
    description = Column(Text, nullable=False)
    budget_type = Column(String(20), default="FIXED")
    budget_min = Column(Numeric(10, 2), default=0)
    budget_max = Column(Numeric(10, 2), default=0)
    required_skills = Column(String(500), default="")
    duration = Column(String(80), default="1-3 months")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class ProjectProposalSQLA(Base):
    __tablename__ = "recruitment_projectproposal"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("recruitment_project.id"), nullable=False)
    freelancer_id = Column(BigInteger, ForeignKey("accounts_user.id"), nullable=False)
    cover_letter = Column(Text, nullable=False)
    bid_amount = Column(Numeric(10, 2), nullable=False)
    estimated_days = Column(Integer, default=14)
    status = Column(String(20), default="PENDING")
    client_notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class JobSQLA(Base):
    __tablename__ = "recruitment_job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    recruiter_id = Column(BigInteger, ForeignKey("accounts_user.id"), nullable=False)
    title = Column(String(180), nullable=False)
    company_name = Column(String(160), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class ApplicationSQLA(Base):
    __tablename__ = "recruitment_application"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id = Column(BigInteger, ForeignKey("accounts_user.id"), nullable=False)
    job_id = Column(BigInteger, ForeignKey("recruitment_job.id"), nullable=False)
    status = Column(String(30), default="PENDING")
    created_at = Column(DateTime(timezone=True), default=_utcnow)


# ==============================================================================
# Analytics & Diagnostic Helper Functions
# ==============================================================================

def get_database_diagnostics() -> dict:
    """
    Returns engine metadata and connectivity status for the owner dashboard.
    Masks the password in the displayed URL.
    """
    engine = get_engine()
    dialect_name = engine.dialect.name.upper()
    db_target = str(engine.url)

    # Mask credentials for display
    if "@" in db_target:
        scheme_user = db_target.split("@")[0]
        host_part = db_target.split("@")[1]
        scheme = scheme_user.split("://")[0]
        db_target = f"{scheme}://***@{host_part}"

    is_connected = False
    error_msg = ""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            is_connected = True
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("[SQLAlchemy] Connectivity check failed: %s", exc)

    return {
        "engine": "SQLAlchemy 2.x",
        "dialect": dialect_name,
        "is_postgresql": "POSTGRES" in dialect_name,
        "target": db_target,
        "is_connected": is_connected,
        "error": error_msg,
    }


def fetch_audit_logs_sqla(limit: int = 50) -> list:
    """Fetches recent audit log entries via SQLAlchemy (read-only)."""
    try:
        with get_sqlalchemy_session() as session:
            logs = (
                session.query(AuditLogSQLA)
                .order_by(AuditLogSQLA.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": log.id,
                    "user_id": log.user_id,
                    "action": log.action,
                    "ip_address": log.ip_address,
                    "details": log.details,
                    "timestamp": log.timestamp,
                }
                for log in logs
            ]
    except Exception as exc:
        logger.error("[SQLAlchemy] fetch_audit_logs_sqla failed: %s", exc)
        return []


def fetch_platform_analytics_sqla() -> dict:
    """Aggregates platform-wide statistics for the owner dashboard."""
    try:
        with get_sqlalchemy_session() as session:
            user_counts = (
                session.query(UserSQLA.role, func.count(UserSQLA.id))
                .group_by(UserSQLA.role)
                .all()
            )
            total_users = session.query(func.count(UserSQLA.id)).scalar() or 0
            total_jobs = session.query(func.count(JobSQLA.id)).scalar() or 0
            total_projects = session.query(func.count(ProjectSQLA.id)).scalar() or 0
            total_applications = session.query(func.count(ApplicationSQLA.id)).scalar() or 0
            total_proposals = session.query(func.count(ProjectProposalSQLA.id)).scalar() or 0

            role_breakdown = {role: count for role, count in user_counts}

            return {
                "total_users": total_users,
                "roles": {
                    "owner": role_breakdown.get("OWNER", 0),
                    "recruiter": role_breakdown.get("RECRUITER", 0),
                    "freelancer": role_breakdown.get("FREELANCER", 0),
                    "candidate": role_breakdown.get("CANDIDATE", 0),
                },
                "total_jobs": total_jobs,
                "total_projects": total_projects,
                "total_applications": total_applications,
                "total_proposals": total_proposals,
            }
    except Exception as exc:
        logger.error("[SQLAlchemy] fetch_platform_analytics_sqla failed: %s", exc)
        return {
            "total_users": 0,
            "roles": {"owner": 0, "recruiter": 0, "freelancer": 0, "candidate": 0},
            "total_jobs": 0,
            "total_projects": 0,
            "total_applications": 0,
            "total_proposals": 0,
        }


def log_audit_event_sqla(
    user_id,
    action: str,
    ip_address: str = "",
    user_agent: str = "",
    details: dict = None,
) -> None:
    """
    Records an audit event directly via SQLAlchemy.
    Silently fails to avoid interrupting user-facing request flows.
    """
    try:
        with get_sqlalchemy_session() as session:
            entry = AuditLogSQLA(
                user_id=user_id,
                action=action,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details or {},
                timestamp=_utcnow(),
            )
            session.add(entry)
    except Exception as exc:
        logger.warning("[SQLAlchemy] log_audit_event_sqla failed silently: %s", exc)
