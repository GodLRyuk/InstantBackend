import hashlib
import ipaddress
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.contrib.auth import get_user_model


LOCKOUT_SECONDS = 15 * 60
RATE_WINDOW_SECONDS = 60
IP_FAILURE_LIMIT = 20
USERNAME_FAILURE_LIMIT = 30
IP_USERNAME_FAILURE_LIMIT = 5
IP_RATE_LIMIT = 20
USERNAME_RATE_LIMIT = 10


@dataclass(frozen=True)
class LoginAttempt:
    ip_address: str
    username: str
    retry_after: int | None = None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cache_key(scope: str, value: str) -> str:
    return f"login-security:{scope}:{_digest(value)}"


def _client_ip(request) -> str:
    header = getattr(settings, "LOGIN_CLIENT_IP_HEADER", "HTTP_X_REAL_IP")
    forwarded_ip = request.META.get(header, "").strip()
    try:
        return str(ipaddress.ip_address(forwarded_ip))
    except ValueError:
        remote_addr = request.META.get("REMOTE_ADDR", "")
        try:
            return str(ipaddress.ip_address(remote_addr))
        except ValueError:
            return "unknown"


def _canonical_username(identifier: str) -> str:
    normalized = identifier.strip().casefold()
    if not normalized:
        return ""

    user_model = get_user_model()
    user = user_model.objects.filter(
        Q(username__iexact=normalized) | Q(email__iexact=normalized)
    ).only("username").first()
    return user.username.casefold() if user else normalized


def _increment(key: str, timeout: int) -> int:
    if cache.add(key, 1, timeout=timeout):
        return 1

    try:
        return cache.incr(key)
    except ValueError:
        if cache.add(key, 1, timeout=timeout):
            return 1
        return cache.incr(key)


def prepare_login_attempt(request, identifier: str | None) -> LoginAttempt:
    ip_address = _client_ip(request)
    username = _canonical_username(identifier or "")
    attempt = LoginAttempt(ip_address=ip_address, username=username)

    lock_keys = [_cache_key("ip-lock", ip_address)]
    if username:
        lock_keys.extend((
            _cache_key("username-lock", username),
            _cache_key("ip-username-lock", f"{ip_address}:{username}"),
        ))

    if any(cache.get(key) for key in lock_keys):
        return LoginAttempt(ip_address, username, LOCKOUT_SECONDS)

    if _increment(_cache_key("ip-rate", ip_address), RATE_WINDOW_SECONDS) > IP_RATE_LIMIT:
        return LoginAttempt(ip_address, username, RATE_WINDOW_SECONDS)

    if username and _increment(
        _cache_key("username-rate", username), RATE_WINDOW_SECONDS
    ) > USERNAME_RATE_LIMIT:
        return LoginAttempt(ip_address, username, RATE_WINDOW_SECONDS)

    return attempt


def record_failed_login(attempt: LoginAttempt) -> None:
    ip_failures = _increment(
        _cache_key("ip-failures", attempt.ip_address), LOCKOUT_SECONDS
    )
    if ip_failures >= IP_FAILURE_LIMIT:
        cache.set(_cache_key("ip-lock", attempt.ip_address), True, LOCKOUT_SECONDS)

    if not attempt.username:
        return

    username_failures = _increment(
        _cache_key("username-failures", attempt.username), LOCKOUT_SECONDS
    )
    if username_failures >= USERNAME_FAILURE_LIMIT:
        cache.set(_cache_key("username-lock", attempt.username), True, LOCKOUT_SECONDS)

    pair = f"{attempt.ip_address}:{attempt.username}"
    pair_failures = _increment(_cache_key("ip-username-failures", pair), LOCKOUT_SECONDS)
    if pair_failures >= IP_USERNAME_FAILURE_LIMIT:
        cache.set(_cache_key("ip-username-lock", pair), True, LOCKOUT_SECONDS)
