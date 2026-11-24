from django.core.management.base import BaseCommand
from accounts.services.rate_limiter import RateLimiter


class Command(BaseCommand):
    help = "Safely reset login lockouts and rate limiting counters for users, IPs, or all portals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--identifier",
            type=str,
            default=None,
            help="Specific user identifier (username, email, or phone number) to clear lockout for.",
        )
        parser.add_argument(
            "--ip",
            type=str,
            default=None,
            help="Client IP address to clear lockout for.",
        )
        parser.add_argument(
            "--portal",
            type=str,
            default=None,
            help="Specific portal (e.g. candidate, owner, hr, freelancer, unified).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Clear all active login lockouts across all users and portals.",
        )

    def handle(self, *args, **options):
        identifier = options.get("identifier")
        ip = options.get("ip")
        portal = options.get("portal")
        clear_all = options.get("all")

        if identifier:
            count = RateLimiter.reset_identifier(identifier)
            if ip and portal:
                RateLimiter.reset_attempts(ip=ip, identifier=identifier, portal=portal)
            self.stdout.write(
                self.style.SUCCESS(
                    f"[HireNexa Security] Successfully cleared login lockout for identifier: '{identifier}' ({count} key(s) reset)."
                )
            )
        elif clear_all or (not identifier and not ip and not portal):
            count = RateLimiter.reset_all()
            self.stdout.write(
                self.style.SUCCESS(
                    f"[HireNexa Security] Successfully cleared all login lockouts across all portals ({count} key(s) reset)."
                )
            )
        elif ip:
            known_portals = ["candidate", "owner", "hr", "freelancer", "unified", "phone_otp", "otp", "default"]
            portals = [portal] if portal else known_portals
            from django.core.cache import cache
            count = 0
            for p in portals:
                k = RateLimiter._key(p, ip, "anonymous")
                if cache.get(k) is not None:
                    cache.delete(k)
                    count += 1
            cache.delete(RateLimiter._ip_key(ip))
            self.stdout.write(
                self.style.SUCCESS(
                    f"[HireNexa Security] Successfully cleared login lockout for IP '{ip}' ({count} key(s) reset)."
                )
            )
