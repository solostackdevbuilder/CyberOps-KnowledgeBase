"""Regression tests for CSV formula injection in the FAA export path.

Chunk 5 review flagged that user-authored FAA content flowed into the CSV
export with csv.QUOTE_ALL but no neutralization of leading `=`, `+`, `-`,
`@`, `|`, `\\t`, `\\r`. A blue-team reviewer opening the CSV in Excel or
Google Sheets would execute any such formula (`=IMPORTXML(...)` exfils,
`=cmd|'/c calc'!A0` commands, `=HYPERLINK(...)` phishes).
"""
import unittest
from datetime import datetime

from app.core.models import FAAItem, Session
from app.modules.red_team.services import (
    _csv_safe,
    _csv_safe_row,
    _faa_action_row,
    _faa_export_row,
)


class CsvSafeHelperTests(unittest.TestCase):
    def test_leaves_benign_values_unchanged(self) -> None:
        for value in ("ok", "finding: lateral movement", "", "192.168.1.1", "?a?b"):
            self.assertEqual(_csv_safe(value), value)

    def test_prefixes_formula_starters(self) -> None:
        cases = {
            "=cmd|'/c calc'!A0": "'=cmd|'/c calc'!A0",
            "+1+2": "'+1+2",
            "-cmd": "'-cmd",
            "@SUM(A1:A10)": "'@SUM(A1:A10)",
            "|pipe|": "'|pipe|",
            "\tleading-tab": "'\tleading-tab",
            "\rcarriage": "'\rcarriage",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_csv_safe(raw), expected)

    def test_does_not_double_escape(self) -> None:
        # Already-escaped values should not be re-escaped. Our helper runs once
        # per export, so the contract is "apply to raw authored text only".
        already = "'=leaked"
        self.assertEqual(_csv_safe(already), already)

    def test_row_helper_applies_to_every_cell(self) -> None:
        row = ["safe", "=IMPORTXML('evil')", "-cmd", "normal"]
        self.assertEqual(
            _csv_safe_row(row),
            ["safe", "'=IMPORTXML('evil')", "'-cmd", "normal"],
        )


class FaaActionRowCsvInjectionTests(unittest.TestCase):
    def _make_item(self, **overrides) -> FAAItem:
        now = datetime(2025, 1, 2, 3, 4, 5)
        defaults = {
            "id": "faa-1",
            "session_id": "sess-1",
            "content": "normal content",
            "classification": "action",
            "timestamp": now,
            "source": "manual",
            "confidence_score": 0.9,
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(overrides)
        return FAAItem(**defaults)

    def _make_session(self, **overrides) -> Session:
        now = datetime(2025, 1, 1)
        defaults = {
            "id": "sess-1",
            "title": "Session 1",
            "operator_name": "tester",
            "terminal_content": "",
            "targets": [],
            "tags": [],
            "tools": [],
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(overrides)
        return Session(**defaults)

    def test_malicious_content_is_neutralized(self) -> None:
        item = self._make_item(content="=cmd|'/c calc'!A0\nsecond line")
        row = _faa_action_row(self._make_session(), item)
        # Title and content columns for actions are columns 1 and 2.
        self.assertTrue(row[1].startswith("'="), f"title not escaped: {row[1]!r}")
        self.assertTrue(row[2].startswith("'="), f"content not escaped: {row[2]!r}")

    def test_malicious_target_is_neutralized(self) -> None:
        item = self._make_item()
        session = self._make_session(targets=["=IMPORTXML(\"https://x\",\"//y\")"])
        row = _faa_action_row(session, item)
        targets_col = row[4]  # 5th column in FAA_ACTIONS_EXPORT_COLUMNS
        self.assertTrue(targets_col.startswith("'="), f"target not escaped: {targets_col!r}")


class FaaExportRowCsvInjectionTests(unittest.TestCase):
    def test_malicious_finding_content_is_neutralized(self) -> None:
        now = datetime(2025, 1, 2, 3, 4, 5)
        item = FAAItem(
            id="faa-2",
            session_id="sess-2",
            content="@SUM(A1:A5)",
            classification="finding",
            severity="high",
            timestamp=now,
            source="manual",
            confidence_score=0.8,
            created_at=now,
            updated_at=now,
        )
        row = _faa_export_row(None, item)
        # Title col 0, content col 1.
        self.assertTrue(row[0].startswith("'@"), f"title not escaped: {row[0]!r}")
        self.assertTrue(row[1].startswith("'@"), f"content not escaped: {row[1]!r}")


if __name__ == "__main__":
    unittest.main()
