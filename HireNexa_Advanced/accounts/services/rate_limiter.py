import logging
import re
import time
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("accounts.security")


def get_default_max_attempts() -> int:
    return int(getattr(settings, "LOGIN_MAX_ATTEMPTS", getattr(settings, "MAX_ATTEMPTS", getattr(settings, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 5))))


def get_default_window_seconds() -> int:
    minutes = getattr(settings, "LOGIN_LOCKOUT_MINUTES", getattr(settings, "LOCKOUT_MINUTES", getattr(settings, "LOGIN_RATE_LIMIT_LOCKOUT_MINUTES", None)))
    if minutes is not None:
        return int(float(minutes) * 60)
    return 60 if getattr(settings, "DEBUG", False) else 900  # 1 min in dev/debug, 15 min in prod


class RateLimiter:
    """
    Enterprise In-Memory / Distributed Cache Rate Limiter for Authentication Endpoints.
    Protects against brute-force password guessing, credential stuffing, and OTP flooding.

    Hardened architecture:
    - Keys are strictly partitioned per-portal + per-IP + per-normalized-identifier:
        rl:{portal}:{client_ip}:{identifier}
      This ensures failures on one portal (e.g. /owner/login/) never lock out other
      portals (e.g. /candidate/login/).
    - Fully configurable via settings (LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MINUTES).
    - Tracks active keys for fast, safe administrative reset via management command.
    """

    @classmethod
    def normalize_identifier(cls, identifier: str) -> str:
        if not identifier:
            return "anonymous"
        ident = str(identifier).strip()
        if "@" in ident:
            return ident.lower()
        digits = re.sub(r"[^\d+]", "", ident)
        if len(re.sub(r"\D", "", digits)) >= 8:
            return digits.lower()
        return ident.lower()

    @classmethod
    def _key(cls, portal: str, ip: str, identifier: str) -> str:
        clean_portal = (portal or "default").strip().lower()
        clean_ip = (ip or "127.0.0.1").strip()
        clean_id = cls.normalize_identifier(identifier)
        return f"rl:{clean_portal}:{clean_ip}:{clean_id}"

    # Legacy key helpers preserved for backwards compatibility with any external caller
    @staticmethod
    def _ip_key(ip: str) -> str:
        clean_ip = (ip or "127.0.0.1").strip()
        return f"rl:ip:{clean_ip}"

    @staticmethod
    def _id_key(identifier: str) -> str:
        clean_id = (identifier or "").strip().lower()
        return f"rl:id:{clean_id}"

    @classmethod
    def _track_key(cls, key: str, identifier: str = None) -> None:
        clean_id = (identifier or "").strip().lower()
        if clean_id:
            idx_id = f"rl:idx:id:{clean_id}"
            keys = set(cache.get(idx_id) or [])
            keys.add(key)
            cache.set(idx_id, list(keys), timeout=86400)

        idx_all = "rl:idx:all"
        all_keys = set(cache.get(idx_all) or [])
        all_keys.add(key)
        cache.set(idx_all, list(all_keys), timeout=86400)

    @classmethod
    def is_rate_limited(
        cls,
        ip: str,
        identifier: str = None,
        portal: str = "default",
        max_attempts: int = None,
        window_seconds: int = None,
    ) -> tuple[bool, int, str]:
        """
        Check whether an IP address + identifier combination on a specific portal
        is currently rate limited.

        Returns:
            (is_blocked: bool, retry_after_seconds: int, reason: str)
        """
        if max_attempts is None:
            max_attempts = get_default_max_attempts()
        if window_seconds is None:
            window_seconds = get_default_window_seconds()

        now = time.time()
        key = cls._key(portal, ip, identifier)
        key_data = cache.get(key)

        if key_data:
            attempts, first_attempt_time = key_data
            elapsed = now - first_attempt_time
            if attempts >= max_attempts and elapsed < window_seconds:
                remaining = int(window_seconds - elapsed)
                return (
                    True,
                    max(remaining, 1),
                    f"Rate limit exceeded on '{portal}' portal ({attempts} failed attempts).",
                )

        return False, 0, ""

    @classmethod
    def record_failed_attempt(
        cls,
        ip: str,
        identifier: str = None,
        portal: str = "default",
        window_seconds: int = None,
    ) -> int:
        """
        Records a failed authentication attempt isolated to the specific portal, IP, and identifier.
        Returns the updated attempt count.
        """
        if window_seconds is None:
            window_seconds = get_default_window_seconds()

        now = time.time()
        key = cls._key(portal, ip, identifier)
        key_data = cache.get(key)

        if key_data:
            attempts, first_attempt_time = key_data
            if now - first_attempt_time < window_seconds:
                attempts += 1
            else:
                attempts = 1
                first_attempt_time = now
        else:
            attempts = 1
            first_attempt_time = now

        remaining_ttl = max(int(window_seconds - (now - first_attempt_time)), 1)
        cache.set(key, (attempts, first_attempt_time), timeout=remaining_ttl)
        cls._track_key(key, identifier)

        logger.warning(
            "Failed login attempt recorded on portal '%s' for IP: %s, Identifier: %s (Count: %d)",
            portal,
            ip,
            identifier,
            attempts,
        )
        return attempts

    @classmethod
    def reset_attempts(cls, ip: str, identifier: str = None, portal: str = None) -> None:
        """
        Clears rate-limiting tracking for the IP, identifier, and portal on successful authentication.
        If portal is omitted, clears across all known portals.
        """
        clean_id = (identifier or "").strip().lower()

        if portal:
            key = cls._key(portal, ip, identifier)
            cache.delete(key)
        else:
            known_portals = ["candidate", "owner", "hr", "freelancer", "unified", "phone_otp", "otp", "default"]
            for p in known_portals:
                cache.delete(cls._key(p, ip, identifier))

        # Also clean legacy keys if they linger
        if ip:
            cache.delete(cls._ip_key(ip))
        if clean_id:
            cache.delete(cls._id_key(clean_id))

    @classmethod
    def reset_identifier(cls, identifier: str) -> int:
        """
        Resets all rate limits for a given identifier across all IPs and portals.
        Returns the count of cleared keys.
        """
        if not identifier:
            return 0

        clean_id = str(identifier).strip().lower()
        idx_id = f"rl:idx:id:{clean_id}"
        keys = set(cache.get(idx_id) or [])
        count = 0

        # Also probe across known portals and common IPs
        known_portals = ["candidate", "owner", "hr", "freelancer", "unified", "phone_otp", "otp", "default"]
        common_ips = ["127.0.0.1", "localhost", "::1"]
        for p in known_portals:
            for cip in common_ips:
                keys.add(cls._key(p, cip, clean_id))

        keys.add(cls._id_key(clean_id))

        for k in keys:
            if cache.get(k) is not None:
                cache.delete(k)
                count += 1

        cache.delete(idx_id)

        # In-memory LocMemCache deep clean if applicable
        if hasattr(cache, "_cache"):
            locmem_keys = [
                k for k in list(cache._cache.keys())
                if clean_id in str(k).lower() and ("rl:" in str(k) or ":1:rl:" in str(k))
            ]
            for lk in locmem_keys:
                cache._cache.pop(lk, None)
                if hasattr(cache, "_expire_info"):
                    cache._expire_info.pop(lk, None)
                count += 1

        return count

    @classmethod
    def reset_all(cls) -> int:
        """
        Resets all active rate-limiting keys across the application.
        Returns the count of cleared keys.
        """
        count = 0
        idx_all = "rl:idx:all"
        all_keys = set(cache.get(idx_all) or [])

        for k in all_keys:
            if cache.get(k) is not None:
                cache.delete(k)
                count += 1
        cache.delete(idx_all)

        # In-memory LocMemCache deep sweep
        if hasattr(cache, "_cache"):
            locmem_keys = [
                k for k in list(cache._cache.keys())
                if "rl:" in str(k) or ":1:rl:" in str(k)
            ]
            for lk in locmem_keys:
                cache._cache.pop(lk, None)
                if hasattr(cache, "_expire_info"):
                    cache._expire_info.pop(lk, None)
                count += 1

        return count
