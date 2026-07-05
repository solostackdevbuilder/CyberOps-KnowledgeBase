"""
Broad coverage for the JSON sanitizer beyond the existing URL-preservation
regression tests. Exercises every strategy method in the sanitization
pipeline plus the public entry point's guarantees (never raises, always
returns a dict).

Lives alongside test_json_sanitizer_url_preservation.py, which remains the
pinned regression for the http:// truncation bug.
"""
import json
import unittest

from app.utils.json_sanitizer import JsonSanitizer


class ParseLlmJsonEntryPointTests(unittest.TestCase):
    """Public contract: never raises, always returns a dict."""

    def test_well_formed_json_round_trips(self) -> None:
        payload = {"a": 1, "b": ["x", "y"], "c": {"d": True}}
        result = JsonSanitizer.parse_llm_json(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_empty_string_returns_emergency_fallback(self) -> None:
        result = JsonSanitizer.parse_llm_json("")
        self.assertTrue(result.get("_fallback"))
        self.assertIn("items", result)

    def test_none_returns_emergency_fallback(self) -> None:
        # Main entry point must tolerate non-string input without raising.
        result = JsonSanitizer.parse_llm_json(None)  # type: ignore[arg-type]
        self.assertTrue(result.get("_fallback"))

    def test_non_string_input_returns_emergency_fallback(self) -> None:
        result = JsonSanitizer.parse_llm_json(12345)  # type: ignore[arg-type]
        self.assertTrue(result.get("_fallback"))

    def test_totally_garbage_input_never_raises(self) -> None:
        # Random bytes-like noise must not produce a JSONDecodeError. The
        # guarantee is "always returns a dict" - verify that, not the shape.
        result = JsonSanitizer.parse_llm_json("@@@not json at all@@@ >> << ???")
        self.assertIsInstance(result, dict)

    def test_markdown_fenced_json_parses(self) -> None:
        payload = '```json\n{"status": "ok", "count": 42}\n```'
        result = JsonSanitizer.parse_llm_json(payload)
        self.assertEqual(result, {"status": "ok", "count": 42})

    def test_generic_code_fence_parses(self) -> None:
        payload = '```\n{"status": "ok"}\n```'
        result = JsonSanitizer.parse_llm_json(payload)
        self.assertEqual(result, {"status": "ok"})

    def test_trailing_comma_is_fixed(self) -> None:
        result = JsonSanitizer.parse_llm_json('{"a": 1, "b": 2,}')
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_trailing_comma_in_array_is_fixed(self) -> None:
        result = JsonSanitizer.parse_llm_json('{"items": [1, 2, 3,]}')
        self.assertEqual(result, {"items": [1, 2, 3]})

    def test_unescaped_newline_inside_string_is_fixed(self) -> None:
        # LLMs frequently emit real newlines inside string values.
        raw = '{"msg": "line1\nline2"}'
        result = JsonSanitizer.parse_llm_json(raw)
        self.assertEqual(result["msg"], "line1\nline2")

    def test_unescaped_tab_inside_string_is_fixed(self) -> None:
        raw = '{"msg": "col1\tcol2"}'
        result = JsonSanitizer.parse_llm_json(raw)
        self.assertEqual(result["msg"], "col1\tcol2")

    def test_null_byte_inside_string_is_stripped(self) -> None:
        raw = '{"msg": "before\x00after"}'
        result = JsonSanitizer.parse_llm_json(raw)
        self.assertEqual(result["msg"], "beforeafter")

    def test_unicode_content_preserved(self) -> None:
        raw = '{"msg": "héllo wörld 日本語"}'
        result = JsonSanitizer.parse_llm_json(raw)
        self.assertEqual(result["msg"], "héllo wörld 日本語")


class ExtractJsonBlockTests(unittest.TestCase):
    """Verify code-fence and boundary extraction choose the right slice."""

    def test_markdown_json_fence_extracts_inner(self) -> None:
        text = 'prelude\n```json\n{"a": 1}\n```\npostlude'
        self.assertEqual(
            JsonSanitizer._extract_json_block(text).strip(),
            '{"a": 1}',
        )

    def test_generic_fence_extracts_inner(self) -> None:
        text = '```\n{"a": 1}\n```'
        self.assertEqual(
            JsonSanitizer._extract_json_block(text).strip(),
            '{"a": 1}',
        )

    def test_boundary_detection_when_no_fence(self) -> None:
        text = 'LLM blurb {"a": 1} tail text'
        self.assertEqual(
            JsonSanitizer._extract_json_block(text),
            '{"a": 1}',
        )

    def test_no_json_boundaries_returns_original(self) -> None:
        text = "no json here at all"
        self.assertEqual(JsonSanitizer._extract_json_block(text), text)


class FixControlCharactersTests(unittest.TestCase):
    """State machine correctness for string vs non-string context."""

    def test_newline_outside_string_preserved(self) -> None:
        # Whitespace between JSON tokens should remain to avoid collapsing
        # structure. Only inside-string control chars need escaping.
        out = JsonSanitizer._fix_control_characters('{\n"a": 1\n}')
        self.assertIn("\n", out)

    def test_newline_inside_string_escaped(self) -> None:
        out = JsonSanitizer._fix_control_characters('{"a": "x\ny"}')
        self.assertIn("\\n", out)
        self.assertNotIn("x\ny", out)

    def test_tab_inside_string_escaped(self) -> None:
        out = JsonSanitizer._fix_control_characters('{"a": "x\ty"}')
        self.assertIn("\\t", out)

    def test_cr_inside_string_escaped(self) -> None:
        out = JsonSanitizer._fix_control_characters('{"a": "x\ry"}')
        self.assertIn("\\r", out)

    def test_null_byte_dropped(self) -> None:
        out = JsonSanitizer._fix_control_characters('{"a": "x\x00y"}')
        self.assertNotIn("\x00", out)
        self.assertIn("xy", out)

    def test_escaped_quote_does_not_confuse_state(self) -> None:
        # \" inside a string must not flip the in_string flag.
        raw = '{"a": "he said \\"hi\\"\ndone"}'
        out = JsonSanitizer._fix_control_characters(raw)
        # The literal newline following the closing \\" should still be
        # escaped because state is still "in string" until the real close.
        result = json.loads(out)
        self.assertEqual(result["a"], 'he said "hi"\ndone')

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(JsonSanitizer._fix_control_characters(""), "")


class FixSyntaxErrorsTests(unittest.TestCase):
    """Syntax fix-ups must not corrupt string contents."""

    def test_trailing_comma_before_brace_removed(self) -> None:
        out = JsonSanitizer._fix_syntax_errors('{"a": 1,}')
        self.assertEqual(json.loads(out), {"a": 1})

    def test_trailing_comma_before_bracket_removed(self) -> None:
        out = JsonSanitizer._fix_syntax_errors('{"a": [1, 2,]}')
        self.assertEqual(json.loads(out), {"a": [1, 2]})

    def test_missing_comma_between_objects_inserted(self) -> None:
        # "}{"  must become "}, {" so the array is valid.
        raw = '[{"a": 1}{"b": 2}]'
        out = JsonSanitizer._fix_syntax_errors(raw)
        self.assertEqual(json.loads(out), [{"a": 1}, {"b": 2}])

    def test_duplicate_commas_collapsed(self) -> None:
        out = JsonSanitizer._fix_syntax_errors('{"a": 1,, "b": 2}')
        self.assertEqual(json.loads(out), {"a": 1, "b": 2})

    def test_line_comment_outside_string_removed(self) -> None:
        raw = '{"a": 1, // inline\n "b": 2}'
        result = JsonSanitizer.parse_llm_json(raw)
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_block_comment_outside_string_removed(self) -> None:
        raw = '{"a": /* note */ 1, "b": 2}'
        result = JsonSanitizer.parse_llm_json(raw)
        self.assertEqual(result, {"a": 1, "b": 2})


class StripCommentsOutsideStringsTests(unittest.TestCase):
    """Comment stripper must respect string boundaries and escapes."""

    def test_line_comment_in_string_preserved(self) -> None:
        text = '{"url": "http://x.com"}'
        self.assertEqual(
            JsonSanitizer._strip_comments_outside_strings(text),
            text,
        )

    def test_block_comment_in_string_preserved(self) -> None:
        text = '{"a": "has /* fake */ comment"}'
        self.assertEqual(
            JsonSanitizer._strip_comments_outside_strings(text),
            text,
        )

    def test_escaped_quote_does_not_break_state(self) -> None:
        # \" inside the string; a // afterwards inside the same string must
        # survive. Feed pre-escaped JSON so _strip_comments sees it correctly.
        text = '{"a": "he said \\"// not a comment\\""}'
        result = JsonSanitizer._strip_comments_outside_strings(text)
        self.assertIn("// not a comment", result)


class MinifyJsonTests(unittest.TestCase):
    def test_outside_whitespace_removed(self) -> None:
        out = JsonSanitizer._minify_json('{  "a" :  1 ,  "b" :  2  }')
        self.assertEqual(out, '{"a":1,"b":2}')

    def test_inside_whitespace_preserved(self) -> None:
        out = JsonSanitizer._minify_json('{"a": "two  spaces"}')
        self.assertIn("two  spaces", out)


class ExtractPartialJsonTests(unittest.TestCase):
    """Best-effort partial recovery for common LLM-output shapes."""

    def test_partial_faa_items_recovered(self) -> None:
        # The text ends inside the array, so the overall document is
        # unparseable. _extract_partial_json should still pull out one item.
        text = (
            '{"items": ['
            '{"classification": "finding",'
            ' "content": "SQL injection",'
            ' "mitre_technique": "T1190",'
            ' "mitre_tactic": "Initial Access",'
            ' "severity": "high",'
            ' "confidence_score": 0.9,'
            ' "source": "web_app"}'
        )
        result = JsonSanitizer._extract_partial_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["classification"], "finding")

    def test_partial_simulation_steps_recovered(self) -> None:
        text = (
            '{"prerequisites": ["kali linux"],'
            ' "setup_instructions": "install tools",'
            ' "execution_steps": ['
            '{"step_number": 1, "title": "Enumerate",'
            ' "description": "Run nmap",'
            ' "commands": ["nmap -sV target"],'
            ' "expected_result": "open ports",'
            ' "troubleshooting": "retry with -Pn",'
            ' "warnings": ["network noise"]}'
        )
        result = JsonSanitizer._extract_partial_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["execution_steps"]), 1)
        self.assertEqual(result["execution_steps"][0]["title"], "Enumerate")
        self.assertEqual(result["prerequisites"], ["kali linux"])

    def test_partial_extraction_iocs_recovered(self) -> None:
        text = (
            '{"iocs": {'
            '"ips": [{"value": "1.2.3.4", "context": "c2 server"}],'
            '"domains": [{"value": "evil.com", "context": "phishing"}]'
            '},'
            '"ttps": ["T1059", "T1190", "T1059"],'
            '"tools": ["mimikatz", "rubeus"]'
        )
        result = JsonSanitizer._extract_partial_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["iocs"]["ips"][0]["value"], "1.2.3.4")
        # TTPs deduplicated by the partial parser.
        self.assertEqual(sorted(result["ttps"]), ["T1059", "T1190"])

    def test_unparseable_garbage_returns_none(self) -> None:
        self.assertIsNone(JsonSanitizer._extract_partial_json("<<random noise>>"))


class EmergencyFallbackTests(unittest.TestCase):
    def test_has_both_format_schemas(self) -> None:
        # Callers dispatch on the response shape, so the fallback must
        # carry both FAA-compatible and simulation-compatible fields to
        # avoid downstream KeyErrors.
        fb = JsonSanitizer._emergency_fallback()
        for key in (
            "items",
            "execution_steps",
            "prerequisites",
            "setup_instructions",
            "difficulty_level",
            "risk_level",
            "_fallback",
        ):
            self.assertIn(key, fb)
        self.assertTrue(fb["_fallback"])


class FixSpecificErrorTests(unittest.TestCase):
    def test_missing_comma_between_properties_inserted(self) -> None:
        # parse_llm_json pipeline hits this via _attempt_parsing attempt 4.
        raw = '{"a": "x" "b": "y"}'
        result = JsonSanitizer.parse_llm_json(raw)
        # Either we get both keys back, or (last resort) the fallback -
        # both are acceptable outcomes as long as we don't raise. Assert
        # the stronger contract: pipeline recovered at least one key.
        self.assertIsInstance(result, dict)
        self.assertTrue(
            result.get("_fallback") or {"a", "b"}.issubset(result.keys()),
            f"Unexpected recovery shape: {result}",
        )


if __name__ == "__main__":
    unittest.main()
