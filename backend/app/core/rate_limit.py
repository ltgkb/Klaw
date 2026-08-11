"""Redis-backed request throttling for public and API-key endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import time
from dataclasses import dataclass
import redis.asyncio as aioredis
from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger("claw.rate_limit")

_RATE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class LimitSpec:
    name: str
    requests: int
    concurrency: int | None = None
    identify_by_api_key: bool = False


class _LocalFallback:
    """Small fail-open fallback that still bounds a single worker if Redis is down."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window: int) -> tuple[int, int]:
        now = time.monotonic()
        async with self._lock:
            count, expires = self._buckets.get(key, (0, now + window))
            if expires <= now:
                count, expires = 0, now + window
            count += 1
            self._buckets[key] = (count, expires)
            if len(self._buckets) > 10_000:
                self._buckets = {
                    item_key: value
                    for item_key, value in self._buckets.items()
                    if value[1] > now
                }
            return count, max(1, int(expires - now))


class RateLimitMiddleware:
    """Apply fixed-window limits and local in-flight bounds to costly routes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        self._fallback = _LocalFallback()
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    @staticmethod
    def _spec(request: Request) -> LimitSpec | None:
        if request.method != "POST":
            return None
        path = request.url.path.rstrip("/")
        if path == "/api/v1/public-chat":
            return LimitSpec(
                "public-chat",
                settings.public_chat_rate_per_minute,
                settings.public_chat_max_concurrency,
            )
        if path == "/api/v1/auth/login":
            return LimitSpec("auth-login", settings.auth_login_rate_per_minute)
        if path == "/api/v1/auth/register":
            return LimitSpec("auth-register", settings.auth_register_rate_per_minute)
        if path == "/api/v1/auth/refresh":
            return LimitSpec("auth-refresh", settings.auth_login_rate_per_minute * 3)
        if path in {
            "/api/v1/supplier-chat",
            "/api/v1/kai-knowledge/chat",
            "/api/v1/kai-knowledge/chat/stream",
        }:
            return LimitSpec(
                "external-api",
                settings.api_key_rate_per_minute,
                settings.api_key_max_concurrency,
                identify_by_api_key=True,
            )
        return None

    @staticmethod
    def _client_ip(request: Request) -> str:
        # The application is bound to loopback; only trust proxy headers from it.
        peer = request.client.host if request.client else "unknown"
        if peer in {"127.0.0.1", "::1", "test"}:
            chain = request.headers.get("x-forwarded-for")
            if chain:
                candidates = [item.strip() for item in chain.split(",") if item.strip()]
                # ALB and nginx append addresses. Walk from the trusted end and
                # prefer the nearest public address, skipping private proxy hops.
                for candidate in reversed(candidates):
                    try:
                        address = ipaddress.ip_address(candidate)
                    except ValueError:
                        continue
                    if not (address.is_private or address.is_loopback or address.is_reserved):
                        return candidate[:64]
                if candidates:
                    return candidates[-1][:64]
            forwarded = request.headers.get("x-real-ip")
            if forwarded:
                return forwarded.strip()[:64]
        return peer[:64]

    @staticmethod
    def _identifier(request: Request, spec: LimitSpec) -> str:
        if spec.identify_by_api_key:
            supplied = request.headers.get("x-api-key", "")
            if not supplied:
                authorization = request.headers.get("authorization", "")
                scheme, _, value = authorization.partition(" ")
                if scheme.lower() == "bearer":
                    supplied = value
            if supplied:
                digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest()[:24]
                return f"key:{digest}"
        return f"ip:{RateLimitMiddleware._client_ip(request)}"

    async def _hit(self, key: str, limit: int) -> tuple[int, int]:
        try:
            result = await self._redis.eval(_RATE_SCRIPT, 1, key, 60)
            return int(result[0]), max(1, int(result[1]))
        except Exception as exc:
            logger.warning("Redis rate limiter unavailable; using local fallback: %s", type(exc).__name__)
            return await self._fallback.hit(key, limit, 60)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if not settings.rate_limit_enabled or settings.environment == "dev":
            await self.app(scope, receive, send)
            return

        spec = self._spec(request)
        if spec is None:
            await self.app(scope, receive, send)
            return

        identifier = self._identifier(request, spec)
        key = f"claw:rate:{spec.name}:{identifier}"
        count, retry_after = await self._hit(key, spec.requests)
        headers = {
            "X-RateLimit-Limit": str(spec.requests),
            "X-RateLimit-Remaining": str(max(0, spec.requests - count)),
        }
        if count > spec.requests:
            headers["Retry-After"] = str(retry_after)
            response = JSONResponse(
                status_code=429,
                content={"success": False, "message": "请求过于频繁，请稍后重试"},
                headers=headers,
            )
            await response(scope, receive, send)
            return

        semaphore = None
        if spec.concurrency:
            semaphore = self._semaphores.setdefault(
                spec.name, asyncio.Semaphore(spec.concurrency)
            )
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=0.05)
            except TimeoutError:
                headers["Retry-After"] = "1"
                response = JSONResponse(
                    status_code=429,
                    content={"success": False, "message": "服务繁忙，请稍后重试"},
                    headers=headers,
                )
                await response(scope, receive, send)
                return

        try:
            async def send_with_rate_headers(message: Message) -> None:
                if message["type"] == "http.response.start":
                    MutableHeaders(scope=message).update(headers)
                await send(message)

            await self.app(scope, receive, send_with_rate_headers)
        finally:
            if semaphore is not None:
                semaphore.release()


class SecurityHeadersMiddleware:
    """Add security headers without BaseHTTPMiddleware task-context side effects."""

    _external_api_paths = {
        "/api/v1/supplier-chat",
        "/api/v1/kai-knowledge/chat",
        "/api/v1/kai-knowledge/chat/stream",
    }

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = request.headers.get("x-request-id") or hashlib.sha256(
            f"{time.time_ns()}:{id(scope)}".encode("utf-8")
        ).hexdigest()[:32]
        path = request.url.path.rstrip("/")

        if request.method == "OPTIONS" and path in self._external_api_paths:
            response = Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Max-Age": "600",
                },
            )
            await response(scope, receive, self._header_sender(request, request_id, send))
            return

        await self.app(scope, receive, self._header_sender(request, request_id, send))

    @staticmethod
    def _header_sender(request: Request, request_id: str, send: Send):
        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                if (
                    settings.environment == "prod"
                    or request.url.scheme == "https"
                    or request.headers.get("x-forwarded-proto") == "https"
                ):
                    headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        return send_with_security_headers
