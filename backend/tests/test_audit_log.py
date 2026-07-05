"""
Tests for AuditLogMiddleware.

Scenarios covered:
- GET requests are not logged (read-only traffic would drown the log).
- POST/PUT/DELETE/PATCH requests produce one JSONL line per request.
- Identity is pulled from X-Forwarded-User / X-Auth-Request-User;
  missing identity defaults to "anonymous".
- Known-secret body fields (password, api_key, private_key, token,
  teams_webhook_url, etc.) are redacted before the record hits disk.
- Body summary is truncated at _BODY_MAX.
- Daily rotation: records written on different UTC dates land in
  different files.
- Non-JSON bodies (file uploads, form posts) summarize as size, not
  content.
- Downstream handler still sees the original body (replay of the
  request stream works).
- Audit-log write failure does NOT crash the request.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.middleware.audit_log import (
    AuditLogMiddleware,
    _log_filename,
    redact,
)


class Payload(BaseModel):
    title: str
    password: Optional[str] = None


def _make_app(audit_dir: Path, now_fn=None) -> FastAPI:
    """Build a FastAPI app with the audit middleware attached.

    Returns the app - tests drive it through httpx.AsyncClient directly
    because starlette 0.27 + httpx 0.28 TestClient have an API skew
    that breaks `TestClient(app=...)`. The same skew affects several
    other test files in this suite; fixing it is separate work.
    """
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware, audit_dir=audit_dir, now_fn=now_fn)

    @app.get("/api/echo")
    async def get_echo():
        return {"ok": True}

    @app.post("/api/echo")
    async def post_echo(payload: Payload):
        return {"received": payload.title, "password_seen": bool(payload.password)}

    @app.put("/api/echo/{id}")
    async def put_echo(id: str, payload: Payload):
        return {"id": id, "title": payload.title}

    @app.delete("/api/echo/{id}")
    async def delete_echo(id: str):
        return {"deleted": id}

    @app.post("/api/upload")
    async def post_upload():
        return {"uploaded": True}

    return app


def _request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    """Synchronous wrapper around an async httpx call against the app."""
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(_run())


class RedactUnitTests(unittest.TestCase):
    def test_redacts_password_case_insensitive(self) -> None:
        r = redact({"Password": "hunter2"})
        self.assertEqual(r["Password"], "[REDACTED]")

    def test_redacts_api_key(self) -> None:
        r = redact({"api_key": "sk-123"})
        self.assertEqual(r["api_key"], "[REDACTED]")

    def test_redacts_nested(self) -> None:
        r = redact({"llm": {"api_key": "secret", "model": "claude"}})
        self.assertEqual(r["llm"]["api_key"], "[REDACTED]")
        self.assertEqual(r["llm"]["model"], "claude")

    def test_redacts_within_list(self) -> None:
        r = redact({"creds": [{"password": "p1"}, {"password": "p2"}]})
        self.assertEqual(r["creds"][0]["password"], "[REDACTED]")
        self.assertEqual(r["creds"][1]["password"], "[REDACTED]")

    def test_redacts_substring_matches(self) -> None:
        # "db_password" and "anthropic_api_key" are real key names on
        # the wire; substring match catches them.
        r = redact({"db_password": "x", "anthropic_api_key": "y"})
        self.assertEqual(r["db_password"], "[REDACTED]")
        self.assertEqual(r["anthropic_api_key"], "[REDACTED]")

    def test_redacts_webhook_urls(self) -> None:
        r = redact({
            "teams_webhook_url": "https://outlook.office.com/webhook/abc",
            "slack_webhook_url": "https://hooks.slack.com/services/xyz",
        })
        self.assertEqual(r["teams_webhook_url"], "[REDACTED]")
        self.assertEqual(r["slack_webhook_url"], "[REDACTED]")

    def test_leaves_non_secret_values_alone(self) -> None:
        r = redact({"title": "Session 1", "tags": ["recon", "nmap"]})
        self.assertEqual(r, {"title": "Session 1", "tags": ["recon", "nmap"]})


class LogFilenameTests(unittest.TestCase):
    def test_includes_utc_date(self) -> None:
        dt = datetime(2026, 4, 19, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(_log_filename(dt), "audit-2026-04-19.jsonl")

    def test_converts_local_time_to_utc(self) -> None:
        # 2026-04-19 01:00 UTC-5 == 2026-04-19 06:00 UTC.
        # Same date. Just check that the filename respects UTC.
        from datetime import timedelta
        tz = timezone(timedelta(hours=-5))
        dt = datetime(2026, 4, 19, 1, 0, tzinfo=tz)
        self.assertEqual(_log_filename(dt), "audit-2026-04-19.jsonl")


class MiddlewareBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_dir = Path(self.tmp.name) / "audit"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _read_records(self) -> list[dict]:
        records = []
        for f in sorted(self.audit_dir.glob("audit-*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
        return records

    def test_get_is_not_logged(self) -> None:
        app = _make_app(self.audit_dir)
        _request(app, "GET", "/api/echo")
        self.assertEqual(self._read_records(), [])

    def test_post_is_logged(self) -> None:
        app = _make_app(self.audit_dir)
        resp = _request(app, "POST", "/api/echo", json={"title": "hi"})
        self.assertEqual(resp.status_code, 200)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["method"], "POST")
        self.assertEqual(r["path"], "/api/echo")
        self.assertEqual(r["status"], 200)
        self.assertIn("timestamp", r)
        self.assertIsInstance(r["duration_ms"], int)

    def test_put_and_delete_logged(self) -> None:
        app = _make_app(self.audit_dir)
        _request(app, "PUT", "/api/echo/xyz", json={"title": "t"})
        _request(app, "DELETE", "/api/echo/xyz")
        records = self._read_records()
        self.assertEqual({r["method"] for r in records}, {"PUT", "DELETE"})

    def test_identity_from_x_forwarded_user(self) -> None:
        app = _make_app(self.audit_dir)
        _request(
            app, "POST", "/api/echo",
            json={"title": "hi"},
            headers={"X-Forwarded-User": "operator@example.test"},
        )
        r = self._read_records()[0]
        self.assertEqual(r["identity"], "operator@example.test")

    def test_identity_from_x_auth_request_user(self) -> None:
        app = _make_app(self.audit_dir)
        _request(
            app, "POST", "/api/echo",
            json={"title": "hi"},
            headers={"X-Auth-Request-User": "bob"},
        )
        r = self._read_records()[0]
        self.assertEqual(r["identity"], "bob")

    def test_identity_defaults_to_anonymous(self) -> None:
        app = _make_app(self.audit_dir)
        _request(app, "POST", "/api/echo", json={"title": "hi"})
        r = self._read_records()[0]
        self.assertEqual(r["identity"], "anonymous")

    def test_password_is_redacted_in_body_summary(self) -> None:
        app = _make_app(self.audit_dir)
        _request(app, "POST", "/api/echo", json={"title": "s1", "password": "hunter2"})
        r = self._read_records()[0]
        self.assertIn("[REDACTED]", r["body_summary"])
        self.assertNotIn("hunter2", r["body_summary"])

    def test_downstream_still_sees_original_body(self) -> None:
        app = _make_app(self.audit_dir)
        resp = _request(app, "POST", "/api/echo", json={"title": "t", "password": "p"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["password_seen"])

    def test_body_summary_truncates_long_payloads(self) -> None:
        app = _make_app(self.audit_dir)
        long_title = "x" * 2000
        _request(app, "POST", "/api/echo", json={"title": long_title})
        r = self._read_records()[0]
        self.assertTrue(r["body_summary"].endswith("...[truncated]"))
        self.assertLessEqual(len(r["body_summary"]), 520)

    def test_non_json_body_summary_is_size_only(self) -> None:
        app = _make_app(self.audit_dir)
        _request(
            app, "POST", "/api/upload",
            content=b"\x00\x01\x02\x03" * 50,
            headers={"Content-Type": "application/octet-stream"},
        )
        r = self._read_records()[0]
        self.assertIsInstance(r["body_summary"], dict)
        self.assertEqual(r["body_summary"]["bytes"], 200)
        self.assertIn("octet-stream", r["body_summary"]["content_type"])

    def test_daily_rotation(self) -> None:
        times = [
            datetime(2026, 4, 19, 23, 59, tzinfo=timezone.utc),
            datetime(2026, 4, 20, 0, 1, tzinfo=timezone.utc),
        ]
        counter = {"i": 0}

        def fake_now():
            t = times[counter["i"]]
            counter["i"] += 1
            return t

        app = _make_app(self.audit_dir, now_fn=fake_now)
        _request(app, "POST", "/api/echo", json={"title": "day1"})
        _request(app, "POST", "/api/echo", json={"title": "day2"})

        files = sorted(self.audit_dir.glob("audit-*.jsonl"))
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0].name, "audit-2026-04-19.jsonl")
        self.assertEqual(files[1].name, "audit-2026-04-20.jsonl")

    def test_write_failure_does_not_break_request(self) -> None:
        app = _make_app(self.audit_dir)
        with patch(
            "app.core.middleware.audit_log.aiofiles.open",
            side_effect=OSError("disk full"),
        ):
            resp = _request(app, "POST", "/api/echo", json={"title": "ok"})
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
