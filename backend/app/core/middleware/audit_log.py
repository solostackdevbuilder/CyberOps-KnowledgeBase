"""
Append-only audit log for state-changing HTTP requests.

CyberOps runs on a team-shared server behind a YubiKey-authenticating
reverse proxy. When something goes wrong ("who kicked off the 3am
exec against client-prod?") or something goes very right ("who
shipped that great finding?") the team needs an answer. Today we have
nothing, so this adds the minimum viable trail.

## What gets logged

Every request whose method is in `LOGGED_METHODS` (POST / PUT / DELETE
/ PATCH). Read-only GETs are not logged - too noisy for too little
value. Upstream health checks, OpenAPI schema polling, and static
asset fetches stay out of the log.

## Where

`data/audit/audit-YYYY-MM-DD.jsonl`, one JSON object per line,
append-only. Daily rotation keyed on UTC date. Rotation happens by
filename - no tricky log-rotate dance, no lock contention.

## What each line contains

- `timestamp` : ISO 8601 UTC, millisecond precision
- `method`    : HTTP method
- `path`      : request path (no query string to avoid accidental
                secret leakage via URL params)
- `identity`  : operator identity from the reverse proxy's
                `X-Forwarded-User` / `X-Auth-Request-User` header, or
                `"anonymous"` if neither is set (dev machine, direct
                access without the gate)
- `client_ip` : request.client.host (what the proxy forwarded, or
                the immediate peer in dev)
- `status`    : HTTP status code of the response
- `duration_ms`: request handling time in milliseconds
- `body_summary`: first `_BODY_MAX` chars of the JSON-ish request
                body with known-secret fields redacted. Non-JSON
                bodies (uploads, form posts) summarize as a size
                indicator rather than content.

## Redaction

Known-secret body keys (`password`, `api_key`, `private_key`,
`key_passphrase`, `token`, `secret`, `teams_webhook_url`,
`slack_webhook_url`) have their value replaced with `"[REDACTED]"`
before being written to the log. The audit log must not become the
new plaintext-secrets file.

## Failure mode

If the audit log cannot be written (disk full, permissions), the
middleware logs a warning and lets the request through. The audit
trail is defense in depth; a write failure must not DoS the
application.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import aiofiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

LOGGED_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

_IDENTITY_HEADERS = ("X-Forwarded-User", "X-Auth-Request-User")

# Keys whose values are redacted in body summaries before hitting disk.
# Case-insensitive match on the key name. Tests cover every entry here.
_REDACT_KEYS = frozenset({
    "password",
    "api_key",
    "private_key",
    "key_passphrase",
    "passphrase",
    "token",
    "secret",
    "teams_webhook_url",
    "slack_webhook_url",
})

_REDACTED = "[REDACTED]"

# Body summaries truncate at this length. Pick something big enough to
# show the shape of a typical request (a FAA create, a settings update)
# but small enough that malicious / oversize bodies do not balloon the
# audit log.
_BODY_MAX = 500


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that appends a JSONL record for every
    state-changing request.

    Attach with `app.add_middleware(AuditLogMiddleware, audit_dir=...)`.
    """

    def __init__(self, app, audit_dir: Path, now_fn: Optional[Callable[[], datetime]] = None):
        super().__init__(app)
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._now_fn = now_fn or (lambda: datetime.now(tz=timezone.utc))

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        if method not in LOGGED_METHODS:
            return await call_next(request)

        # Buffer the request body so we can both summarize it and
        # hand it to downstream handlers.
        body_bytes = await request.body()

        async def _replay_receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = _replay_receive  # type: ignore[attr-defined]

        started = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)

        # One clock read per request - keeps the record timestamp and
        # the destination filename mutually consistent under a frozen
        # test clock.
        now = self._now_fn()

        # Build the record. Never let a malformed body, missing header,
        # or unexpected type blow up the request.
        try:
            record = {
                "timestamp": now.isoformat(timespec="milliseconds"),
                "method": method,
                "path": request.url.path,
                "identity": _extract_identity(request),
                "client_ip": request.client.host if request.client else None,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "body_summary": _summarize_body(
                    body_bytes, request.headers.get("content-type", "")
                ),
            }
        except Exception as e:  # defensive
            logger.warning("Audit record construction failed: %s", e)
            return response

        try:
            target = self.audit_dir / _log_filename(now)
            async with aiofiles.open(target, "a", encoding="utf-8") as f:
                await f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(
                "Failed to append audit log for %s %s: %s",
                method, request.url.path, e,
            )

        return response


def _extract_identity(request: Request) -> str:
    for header in _IDENTITY_HEADERS:
        value = request.headers.get(header)
        if value:
            return value
    return "anonymous"


def _log_filename(now: datetime) -> str:
    return f"audit-{now.astimezone(timezone.utc).strftime('%Y-%m-%d')}.jsonl"


def _summarize_body(body_bytes: bytes, content_type: str) -> Any:
    """Return a redacted summary of the request body.

    - JSON bodies: parse, redact known-secret keys recursively,
      re-serialize, truncate to `_BODY_MAX`.
    - Non-JSON bodies: return `{"content_type": ..., "bytes": N}`.
    - Parse failures: fall back to a length-only summary.
    """
    if not body_bytes:
        return ""

    ctype = content_type.lower()
    if "application/json" in ctype:
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {"content_type": "application/json", "bytes": len(body_bytes), "parse_error": True}
        redacted = redact(parsed)
        serialized = json.dumps(redacted, ensure_ascii=False)
        if len(serialized) > _BODY_MAX:
            return serialized[:_BODY_MAX] + "...[truncated]"
        return serialized

    return {"content_type": ctype or "unknown", "bytes": len(body_bytes)}


def redact(obj: Any) -> Any:
    """Recursively replace known-secret values with [REDACTED].

    Exposed at module level so the audit middleware and tests share one
    definition of what counts as a secret. Works on arbitrary
    JSON-shaped structures (dict / list / str / number / bool / None).
    """
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if _should_redact_key(key):
                out[key] = _REDACTED
            else:
                out[key] = redact(value)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def _should_redact_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in _REDACT_KEYS:
        return True
    # Substring match for things like "db_password" or "anthropic_api_key".
    return any(secret in lowered for secret in _REDACT_KEYS if len(secret) >= 5)


def iter_audit_files(audit_dir: Path) -> Iterable[Path]:
    """Yield every audit-YYYY-MM-DD.jsonl file in `audit_dir`, sorted."""
    if not audit_dir.exists():
        return []
    return sorted(p for p in audit_dir.iterdir() if p.name.startswith("audit-") and p.suffix == ".jsonl")
