"""
Tests for startup guards.

check_network_binding_policy takes an optional `env` mapping for tests
so we can exercise every branch without mutating os.environ.
"""
import unittest

from app.core.startup_guards import (
    BIND_HOST_ENV,
    TRUST_NETWORK_ENV,
    StartupGuardError,
    check_network_binding_policy,
)


class NetworkBindingPolicyTests(unittest.TestCase):
    def test_empty_env_passes(self) -> None:
        # Tests and default uvicorn runs have no env var set. The guard
        # must let them through - it gates the dangerous case only.
        check_network_binding_policy(env={})

    def test_loopback_bind_passes(self) -> None:
        check_network_binding_policy(env={BIND_HOST_ENV: "127.0.0.1"})

    def test_localhost_hostname_passes(self) -> None:
        # A deployment that binds to "localhost" rather than "127.0.0.1"
        # is still private - the guard only fires on all-interfaces binds.
        check_network_binding_policy(env={BIND_HOST_ENV: "localhost"})

    def test_specific_interface_passes(self) -> None:
        # An operator who binds to a specific internal IP is making an
        # explicit choice; the guard stays out of the way.
        check_network_binding_policy(env={BIND_HOST_ENV: "10.0.0.5"})

    def test_public_bind_without_trust_refuses(self) -> None:
        with self.assertRaises(StartupGuardError) as ctx:
            check_network_binding_policy(env={BIND_HOST_ENV: "0.0.0.0"})
        msg = str(ctx.exception)
        # Message must name the offending value and the escape hatch.
        self.assertIn("0.0.0.0", msg)
        self.assertIn(TRUST_NETWORK_ENV, msg)
        self.assertIn("reverse proxy", msg.lower())

    def test_public_bind_with_trust_passes(self) -> None:
        check_network_binding_policy(env={
            BIND_HOST_ENV: "0.0.0.0",
            TRUST_NETWORK_ENV: "1",
        })

    def test_ipv6_all_interfaces_also_gated(self) -> None:
        with self.assertRaises(StartupGuardError):
            check_network_binding_policy(env={BIND_HOST_ENV: "::"})

    def test_ipv6_with_trust_passes(self) -> None:
        check_network_binding_policy(env={
            BIND_HOST_ENV: "::",
            TRUST_NETWORK_ENV: "1",
        })

    def test_non_one_trust_value_does_not_count(self) -> None:
        # Strictly '1' - a '0' or 'true' or 'yes' suggests the operator
        # was guessing at the syntax; fail loudly rather than accept.
        for other in ("0", "true", "yes", "TRUE", "enabled", ""):
            with self.subTest(trust=other):
                with self.assertRaises(StartupGuardError):
                    check_network_binding_policy(env={
                        BIND_HOST_ENV: "0.0.0.0",
                        TRUST_NETWORK_ENV: other,
                    })

    def test_whitespace_around_bind_host_still_triggers(self) -> None:
        # Shell expansion or .env leaks can add whitespace; the guard
        # must not be bypassable by padding.
        with self.assertRaises(StartupGuardError):
            check_network_binding_policy(env={BIND_HOST_ENV: "  0.0.0.0  "})

    def test_whitespace_around_trust_accepted(self) -> None:
        # Padding on the trust value must still count as '1'; operators
        # write env files by hand and whitespace is common.
        check_network_binding_policy(env={
            BIND_HOST_ENV: "0.0.0.0",
            TRUST_NETWORK_ENV: " 1 ",
        })


if __name__ == "__main__":
    unittest.main()
