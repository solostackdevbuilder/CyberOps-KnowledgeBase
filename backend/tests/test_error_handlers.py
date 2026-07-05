"""
Tests for the catch-all unhandled-exception handler.

Scenarios covered:
- A route that raises a bare Exception returns the generic
  `{"error": "internal_error", "correlation_id": ...}` shape with 500.
- The response does NOT include the Python exception message, file
  path, or traceback (the leak we're trying to close).
- Two concurrent requests get distinct correlation ids.
- Correlation id is short (~12 hex chars), copy-pasteable.
- The full exception and traceback land in the server log keyed by
  the same correlation id so operators can diagnose.
- Pre-existing typed-exception handlers (e.g., StorageNotFoundError)
  still produce their structured responses - the catch-all does not
  shadow them.
- HTTPException with a specific status code still passes through.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unittest

import httpx
from fastapi import FastAPI, HTTPException

from app.core.error_handlers import register_exception_handlers
from app.core.exceptions import StorageNotFoundError


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("internal secret path /srv/x/y leaked here")

    @app.get("/api/divide-by-zero")
    async def divzero():
        return {"result": 1 / 0}

    @app.get("/api/not-found")
    async def not_found():
        raise StorageNotFoundError("session", "does-not-exist")

    @app.get("/api/teapot")
    async def teapot():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    return app


def _get(app: FastAPI, path: str) -> httpx.Response:
    async def _run():
        # raise_app_exceptions=False: let the app's exception handlers
        # produce a response instead of httpx re-raising the underlying
        # exception. Without this, bare RuntimeError in the handler
        # would bubble out of the client call and never exercise our
        # catch-all.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)
    return asyncio.run(_run())


class UnhandledExceptionTests(unittest.TestCase):
    def test_runtime_error_returns_generic_shape(self) -> None:
        app = _build_app()
        resp = _get(app, "/api/boom")
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["error"], "internal_error")
        self.assertIn("correlation_id", body)
        self.assertIsInstance(body["correlation_id"], str)

    def test_exception_message_does_not_leak(self) -> None:
        app = _build_app()
        resp = _get(app, "/api/boom")
        body = resp.text
        self.assertNotIn("internal secret path", body)
        self.assertNotIn("/srv/x/y", body)
        self.assertNotIn("RuntimeError", body)
        self.assertNotIn("Traceback", body)

    def test_correlation_id_is_short_hex(self) -> None:
        app = _build_app()
        resp = _get(app, "/api/boom")
        cid = resp.json()["correlation_id"]
        self.assertRegex(cid, r"^[0-9a-f]{12}$")

    def test_two_requests_get_distinct_correlation_ids(self) -> None:
        app = _build_app()
        a = _get(app, "/api/boom").json()["correlation_id"]
        b = _get(app, "/api/boom").json()["correlation_id"]
        self.assertNotEqual(a, b)

    def test_server_log_contains_exception_and_correlation_id(self) -> None:
        app = _build_app()
        with self.assertLogs("app.core.error_handlers", level="ERROR") as logs:
            resp = _get(app, "/api/boom")
        cid = resp.json()["correlation_id"]
        joined = "\n".join(logs.output)
        # Full exception name must appear in the server log (we want it
        # there to diagnose) - but NOT in the client response (we
        # already asserted that above).
        self.assertIn("RuntimeError", joined)
        self.assertIn("internal secret path", joined)
        # Correlation id ties log to response.
        self.assertIn(cid, joined)

    def test_zero_division_is_also_caught(self) -> None:
        """Arbitrary uncaught Python errors go through the catch-all."""
        app = _build_app()
        resp = _get(app, "/api/divide-by-zero")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"], "internal_error")
        self.assertNotIn("ZeroDivisionError", resp.text)


class TypedExceptionPassthroughTests(unittest.TestCase):
    def test_storage_not_found_still_returns_404_shape(self) -> None:
        """The catch-all must not shadow the typed handlers."""
        app = _build_app()
        resp = _get(app, "/api/not-found")
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body["error"], "not_found")
        self.assertEqual(body["resource_type"], "session")
        self.assertEqual(body["resource_id"], "does-not-exist")

    def test_http_exception_passes_through(self) -> None:
        app = _build_app()
        resp = _get(app, "/api/teapot")
        self.assertEqual(resp.status_code, 418)
        self.assertEqual(resp.json(), {"detail": "I'm a teapot"})


if __name__ == "__main__":
    unittest.main()
