"""
Integration tests for the LLM validation pipeline.

`services_validated.analyze_session_for_faa_validated` is the most
load-bearing red-team path in the app. It chains:

    LLM.query() -> JSON sanitizer -> HallucinationGuard -> FAAItem

This file provides end-to-end coverage across four scenarios:

1. Well-formed response: LLM returns clean JSON with an item grounded
   in the terminal content. Pipeline should return exactly one
   validated item.
2. Fabricated IOC: LLM returns an item that mentions an IP the source
   terminal content never saw. The HallucinationGuard's grounding
   check should flag it - we assert the validation summary surfaces
   the issue.
3. Invalid MITRE technique: LLM returns an item with a bogus
   technique id. With strict validation on, the pipeline clears the
   technique rather than letting it flow downstream as truth.
4. Emergency fallback: LLM returns unparseable garbage. The sanitizer
   kicks in with the `_fallback` marker and the pipeline returns an
   empty-items response with a JSON-parse warning instead of raising.

Each test mocks BaseLLM and the storage layer; nothing touches real
providers, real storage, or the filesystem. Tests run in <1 second
total.
"""
from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

from app.core.models import Session
from app.modules.red_team.services_validated import (
    ValidationConfig,
    analyze_session_for_faa_validated,
)


def _run(coro):
    return asyncio.run(coro)


def _session(terminal_content: str) -> Session:
    now = datetime.utcnow()
    return Session(
        id="sess-pipeline-test",
        title="Pipeline test session",
        description=None,
        tags=[],
        operation_id="op-1",
        operator_name="tester",
        terminal_content=terminal_content,
        screenshots=[],
        screenshot_extractions=[],
        created_at=now,
        updated_at=now,
    )


def _fake_llm(response_text: str) -> MagicMock:
    """Return a MagicMock shaped like BaseLLM with query() → response_text."""
    llm = MagicMock()
    llm.query = AsyncMock(return_value=response_text)
    return llm


def _fake_storage(session: Optional[Session]) -> MagicMock:
    storage = MagicMock()
    storage.get_session = AsyncMock(return_value=session)
    return storage


class WellFormedResponseTests(unittest.TestCase):
    def test_grounded_item_is_returned_with_high_confidence(self) -> None:
        # Source data: a real nmap run against 10.0.0.1. Any IP the LLM
        # mentions must be one that appears here, or the grounding
        # check will flag it.
        terminal = (
            "root@kali:~# nmap -sV 10.0.0.1\n"
            "Starting Nmap scan\n"
            "PORT     STATE SERVICE VERSION\n"
            "22/tcp   open  ssh     OpenSSH 8.2\n"
            "80/tcp   open  http    nginx 1.18\n"
        )
        session = _session(terminal)

        llm_response = json.dumps({
            "items": [
                {
                    "classification": "action",
                    "content": "nmap -sV 10.0.0.1",
                    "output": "SSH (22) and HTTP (80) open",
                    "mitre_technique": "T1046 - Network Service Discovery",
                    "mitre_tactic": "Discovery",
                    "source": "terminal",
                    "confidence_score": 0.9,
                }
            ]
        })

        result = _run(analyze_session_for_faa_validated(
            "sess-pipeline-test",
            _fake_storage(session),
            _fake_llm(llm_response),
        ))

        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item.classification, "action")
        self.assertIn("nmap", item.content)
        # T1046 is a real MITRE technique id. The normalized technique
        # must start with the id.
        self.assertTrue(item.mitre_technique.startswith("T1046"))
        # Summary shape sanity-check.
        summary = result["validation_summary"]
        self.assertEqual(summary["total_items_from_llm"], 1)
        self.assertEqual(summary["validated_items"], 1)
        self.assertEqual(summary["dropped_items"], 0)


class FabricatedIOCTests(unittest.TestCase):
    def test_response_with_ungrounded_ip_is_flagged(self) -> None:
        # Source never mentions 203.0.113.77. The LLM response
        # fabricates it. The grounding check must flag this; the
        # validation summary records at least one grounding issue.
        terminal = "root@kali:~# whoami\nroot\n"
        session = _session(terminal)

        llm_response = json.dumps({
            "items": [
                {
                    "classification": "finding",
                    "content": "Reachable host discovered at 203.0.113.77",
                    "output": "203.0.113.77 responded",
                    "mitre_technique": "T1046 - Network Service Discovery",
                    "mitre_tactic": "Discovery",
                    "severity": "medium",
                    "source": "terminal",
                    "confidence_score": 0.95,
                }
            ]
        })

        result = _run(analyze_session_for_faa_validated(
            "sess-pipeline-test",
            _fake_storage(session),
            _fake_llm(llm_response),
        ))

        summary = result["validation_summary"]
        # The guard may drop the item OR return it with a warning and
        # a reduced confidence - both are acceptable outcomes of
        # "fabricated IOC detected." The assertion is that ONE of
        # those two things happened, not silent pass-through.
        grounding_flagged = summary["grounding_issues"] >= 1
        confidence_penalized = (
            summary["validated_items"] == 0
            or (result["items"] and result["items"][0].confidence_score < 0.95)
        )
        self.assertTrue(
            grounding_flagged or confidence_penalized,
            f"Fabricated IP should surface in validation summary "
            f"or in reduced confidence; got {summary}",
        )


class InvalidMitreTests(unittest.TestCase):
    def test_bogus_technique_id_is_stripped_under_strict_validation(self) -> None:
        # The LLM invents "T9999.001" which is not a real MITRE
        # technique id. With strict validation on, the pipeline must
        # clear the technique on the returned item rather than
        # silently passing a hallucinated id to downstream analysis.
        terminal = "root@kali:~# whoami\nroot\n"
        session = _session(terminal)

        llm_response = json.dumps({
            "items": [
                {
                    "classification": "action",
                    "content": "whoami",
                    "output": "root",
                    "mitre_technique": "T9999.001 - Fake Technique That Does Not Exist",
                    "mitre_tactic": "Discovery",
                    "source": "terminal",
                    "confidence_score": 0.7,
                }
            ]
        })

        result = _run(analyze_session_for_faa_validated(
            "sess-pipeline-test",
            _fake_storage(session),
            _fake_llm(llm_response),
            ValidationConfig(STRICT_MITRE_VALIDATION=True, ENABLE_AUTO_CORRECTION=False),
        ))

        # Either the item is dropped entirely, or it comes back with
        # mitre_technique cleared. Either way, the bogus id must NOT
        # appear on any returned item.
        for item in result["items"]:
            if item.mitre_technique:
                self.assertFalse(
                    item.mitre_technique.startswith("T9999"),
                    f"Bogus technique leaked to returned item: {item.mitre_technique}",
                )
        # A warning must call out the invalid technique so operators
        # can audit what the LLM tried to do.
        warnings_joined = " | ".join(result["warnings"])
        self.assertTrue(
            "T9999" in warnings_joined or "invalid" in warnings_joined.lower(),
            f"Expected a warning about the invalid technique; got {result['warnings']}",
        )


class EmergencyFallbackTests(unittest.TestCase):
    def test_unparseable_response_produces_empty_items_not_exception(self) -> None:
        # LLM returns something that isn't JSON at all. The sanitizer
        # kicks in with its `_fallback` structure and the pipeline
        # must return an empty-items response - not bubble the parse
        # failure up as a 500 to the client.
        session = _session("root@kali:~# whoami\nroot\n")
        llm_response = "I'm sorry, I can't classify this session right now."

        result = _run(analyze_session_for_faa_validated(
            "sess-pipeline-test",
            _fake_storage(session),
            _fake_llm(llm_response),
        ))

        self.assertEqual(result["items"], [])
        # Fallback summary marks the JSON parse failure so operators
        # can see why nothing came back.
        summary = result["validation_summary"]
        self.assertEqual(summary["validated_items"], 0)
        # Either the structured error key is set OR the warnings
        # mention JSON - both paths are acceptable for the fallback.
        fallback_indicator = (
            summary.get("error") == "JSON parse error"
            or any("malformed" in w.lower() or "json" in w.lower() or "parsing" in w.lower()
                   for w in result["warnings"])
        )
        self.assertTrue(
            fallback_indicator,
            f"Fallback path must mark the parse failure; got "
            f"summary={summary} warnings={result['warnings']}",
        )


class MissingSessionTests(unittest.TestCase):
    def test_unknown_session_id_raises_runtime_error(self) -> None:
        """Defensive guard: storage returns None for a bad id. The
        caller should see a RuntimeError - the generic unhandled
        handler in Phase 3.4 will convert it to 500+correlation_id
        for the actual HTTP response."""
        result_storage = _fake_storage(None)
        with self.assertRaises(RuntimeError):
            _run(analyze_session_for_faa_validated(
                "not-a-real-session",
                result_storage,
                _fake_llm("{}"),
            ))


if __name__ == "__main__":
    unittest.main()
