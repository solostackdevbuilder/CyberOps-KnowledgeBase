import unittest

from app.core.services.privacy_transform import (
    NerDetector,
    PrivacyLeakBlockedError,
    PrivacyTransformService,
    StaticRuleDetector,
)
from app.models_settings import (
    EntityGroup,
    SensitiveDefaultsConfig,
    SensitiveKeywordRule,
    SensitiveRegexRule,
    SensitiveRuleSeverity,
    PrivacyMatchType,
    PrivacyReplacementRule,
    PrivacyReplacementSettings,
    Settings,
)


class InMemorySettingsStore:
    def __init__(self, app_settings: Settings):
        self._settings = app_settings

    async def load_settings(self) -> Settings:
        return self._settings

    async def save_settings(self, settings: Settings) -> None:
        self._settings = settings


def make_settings(rules: list[PrivacyReplacementRule]) -> Settings:
    return Settings(
        privacy_replacements=PrivacyReplacementSettings(
            enabled=True,
            restore_on_output=True,
            rules=rules,
        )
    )


class PrivacyTransformServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_trip_domain_replacement(self) -> None:
        service = PrivacyTransformService(
            settings_store=InMemorySettingsStore(
                make_settings(
                    [
                        PrivacyReplacementRule(
                            id="domain",
                            before="shop.disney.com",
                            after="something.example.com",
                            match_type=PrivacyMatchType.SUBSTRING,
                            case_sensitive=False,
                            whole_word=False,
                        )
                    ]
                )
            )
        )

        outbound = await service.sanitize_for_llm("Target is shop.disney.com in this session.")
        self.assertIn(".example.com", outbound.text)
        self.assertNotIn("shop.disney.com", outbound.text)

        inbound = await service.restore_for_ui(outbound.text)
        self.assertIn("shop.disney.com", inbound.text)
        self.assertNotIn("something.example.com", inbound.text)

    async def test_longest_rule_wins_for_overlap(self) -> None:
        rules = [
            PrivacyReplacementRule(
                id="short",
                before="disney corp",
                after="company",
                match_type=PrivacyMatchType.SUBSTRING,
                case_sensitive=False,
                whole_word=False,
            ),
            PrivacyReplacementRule(
                id="long",
                before="the disney corporation",
                after="org_alias",
                match_type=PrivacyMatchType.SUBSTRING,
                case_sensitive=False,
                whole_word=False,
            ),
        ]
        service = PrivacyTransformService(
            settings_store=InMemorySettingsStore(make_settings(rules))
        )

        outbound = await service.sanitize_for_llm("the disney corporation")
        self.assertEqual(outbound.text, "org_alias")

    async def test_recursive_restore_for_structured_payload(self) -> None:
        rule = PrivacyReplacementRule(
            id="domain",
            before="shop.disney.com",
            after="something.example.com",
            match_type=PrivacyMatchType.SUBSTRING,
            case_sensitive=False,
            whole_word=False,
        )
        service = PrivacyTransformService(
            settings_store=InMemorySettingsStore(make_settings([rule]))
        )

        payload = {
            "summary": "Investigated something.example.com",
            "items": ["something.example.com", {"nested": "something.example.com/path"}],
        }
        restored = await service.restore_structure_for_ui(payload)

        self.assertEqual(restored["summary"], "Investigated shop.disney.com")
        self.assertEqual(restored["items"][0], "shop.disney.com")
        self.assertEqual(restored["items"][1]["nested"], "shop.disney.com/path")

    async def test_entity_group_terms_are_compiled_into_runtime_rules(self) -> None:
        settings = Settings(
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                entity_groups=[
                    EntityGroup(
                        id="group1",
                        name="Disney",
                        seed_name="Disney",
                        associated_terms=["ESPN", "Hulu"],
                        enabled=True,
                    )
                ],
            )
        )
        service = PrivacyTransformService(settings_store=InMemorySettingsStore(settings))
        outbound = await service.sanitize_for_llm("Disney owns ESPN and Hulu.")
        self.assertIn("org_disney_term_001", outbound.text)
        self.assertIn("org_disney_term_002", outbound.text)
        self.assertIn("org_disney_term_003", outbound.text)

    async def test_domain_alias_is_stable_for_same_domain(self) -> None:
        settings = Settings(
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                strict_privacy_mode=True,
                domain_alias_config={"enabled": True, "alias_suffix": "example.com", "stable_scope": "global"},
                entity_groups=[
                    EntityGroup(
                        id="group1",
                        name="Disney",
                        seed_name="disney",
                        associated_terms=[],
                        enabled=True,
                    )
                ],
            )
        )
        service = PrivacyTransformService(settings_store=InMemorySettingsStore(settings))

        first = await service.sanitize_for_llm("Use shop.disney.com for testing")
        second = await service.sanitize_for_llm("Use shop.disney.com for testing again")
        self.assertNotIn("shop.disney.com", first.text)
        self.assertIn(".example.com", first.text)
        self.assertEqual(first.text.split(" ")[1], second.text.split(" ")[1])

    async def test_regex_sensitive_values_round_trip_via_runtime_tokens(self) -> None:
        settings = Settings(
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                sensitive_defaults=SensitiveDefaultsConfig(
                    enabled=True,
                    keyword_rules=[],
                    regex_rules=[
                        SensitiveRegexRule(
                            id="jwt",
                            name="JWT",
                            pattern=r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
                            replacement="[REDACTED_JWT]",
                            severity=SensitiveRuleSeverity.CRITICAL,
                            enabled=True,
                        )
                    ],
                ),
            )
        )
        service = PrivacyTransformService(settings_store=InMemorySettingsStore(settings))
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmno.pqrstuvwxyz12345"
        outbound = await service.sanitize_for_llm(f"Authorization: Bearer {token}")
        self.assertIn("[[PRIV_SENSITIVE-RX-JWT_", outbound.text)
        self.assertNotIn(token, outbound.text)

        inbound = await service.restore_for_ui(outbound.text)
        self.assertIn(token, inbound.text)

    async def test_custom_regex_rules_on_privacy_round_trip(self) -> None:
        settings = Settings(
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                sensitive_defaults=SensitiveDefaultsConfig(
                    enabled=False,
                    keyword_rules=[],
                    regex_rules=[],
                ),
                custom_regex_rules=[
                    SensitiveRegexRule(
                        id="cust-digits",
                        name="Long digit runs",
                        pattern=r"\b\d{4,}\b",
                        replacement="[REDACTED]",
                        severity=SensitiveRuleSeverity.HIGH,
                        enabled=True,
                    )
                ],
            )
        )
        service = PrivacyTransformService(settings_store=InMemorySettingsStore(settings))
        outbound = await service.sanitize_for_llm("Code 987654 is secret")
        self.assertNotIn("987654", outbound.text)
        self.assertIn("[[PRIV_SENSITIVE-RX-CUST-DIGITS_", outbound.text)
        inbound = await service.restore_for_ui(outbound.text)
        self.assertIn("987654", inbound.text)

    async def test_regex_runs_before_keyword_rules_for_bearer_token(self) -> None:
        """Regression: keyword replacement must not destroy context required by value-extracting regex.

        `kw-authorization` and `kw-bearer` previously ran before `rx-bearer-header`, leaving opaque
        bearer tokens on the wire after the context (``authorization:`` / ``bearer ``) was stripped.
        """
        settings = Settings(
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                sensitive_defaults=SensitiveDefaultsConfig(
                    enabled=True,
                    keyword_rules=[
                        SensitiveKeywordRule(
                            id="kw-authorization",
                            name="Authorization header",
                            keyword="authorization:",
                            replacement="[REDACTED_AUTH_HEADER]",
                            severity=SensitiveRuleSeverity.CRITICAL,
                        ),
                        SensitiveKeywordRule(
                            id="kw-bearer",
                            name="Bearer token marker",
                            keyword="bearer ",
                            replacement="[REDACTED_BEARER]",
                            severity=SensitiveRuleSeverity.CRITICAL,
                        ),
                    ],
                    regex_rules=[
                        SensitiveRegexRule(
                            id="rx-bearer-header",
                            name="Bearer authorization value",
                            pattern=r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-+/=]{16,}",
                            replacement="[REDACTED_BEARER_HEADER]",
                            severity=SensitiveRuleSeverity.CRITICAL,
                        ),
                    ],
                ),
            )
        )
        service = PrivacyTransformService(settings_store=InMemorySettingsStore(settings))
        opaque_token = "abc123def456ghi789xyz"
        outbound = await service.sanitize_for_llm(f"Authorization: Bearer {opaque_token}")

        self.assertNotIn(opaque_token, outbound.text)
        self.assertTrue(
            any(rid.endswith("rx-bearer-header") for rid in outbound.applied_rule_ids),
            f"expected rx-bearer-header to fire, got applied_rule_ids={outbound.applied_rule_ids}",
        )

    async def test_strict_mode_blocks_unmasked_rule_value(self) -> None:
        """strict_privacy_mode must block outbound leak of any `rule.before` value, not just domains."""
        service = PrivacyTransformService(
            settings_store=InMemorySettingsStore(
                Settings(
                    privacy_replacements=PrivacyReplacementSettings(
                        enabled=True,
                        restore_on_output=True,
                        strict_privacy_mode=True,
                        rules=[
                            PrivacyReplacementRule(
                                id="confidential-phrase",
                                before="project phoenix",
                                after="project alpha",
                                match_type=PrivacyMatchType.EXACT,
                                case_sensitive=False,
                                whole_word=True,
                            )
                        ],
                    )
                )
            )
        )

        # Unrelated input does not trip strict mode.
        safe = await service.sanitize_for_llm("nothing sensitive here")
        self.assertEqual(safe.text, "nothing sensitive here")

        # Substring that the rule's whole-word pattern cannot match keeps the value in flight.
        with self.assertRaises(PrivacyLeakBlockedError):
            await service.sanitize_for_llm("roadmap: project phoenix2 launch")

    async def test_runtime_tokens_cleared_after_restore(self) -> None:
        """Restore must drop consumed runtime tokens so they don't leak into later requests."""
        settings = Settings(
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                sensitive_defaults=SensitiveDefaultsConfig(
                    enabled=True,
                    keyword_rules=[],
                    regex_rules=[
                        SensitiveRegexRule(
                            id="jwt",
                            name="JWT",
                            pattern=r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
                            replacement="[REDACTED_JWT]",
                            severity=SensitiveRuleSeverity.CRITICAL,
                            enabled=True,
                        )
                    ],
                ),
            )
        )
        service = PrivacyTransformService(settings_store=InMemorySettingsStore(settings))
        token_value = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmno.pqrstuvwxyz12345"

        outbound = await service.sanitize_for_llm(token_value)
        self.assertTrue(service._runtime_token_map, "sanitize should produce at least one runtime token")

        await service.restore_for_ui(outbound.text)
        self.assertEqual(
            service._runtime_token_map,
            {},
            "consumed runtime tokens must be removed to prevent cross-request leakage",
        )

    def test_invalid_custom_regex_pattern_rejected(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PrivacyReplacementSettings(
                custom_regex_rules=[
                    SensitiveRegexRule(
                        id="bad",
                        name="bad",
                        pattern="(",
                        replacement="x",
                        severity=SensitiveRuleSeverity.HIGH,
                        enabled=True,
                    )
                ]
            )


class DetectorAbstractionTests(unittest.TestCase):
    def test_static_detector_uses_rule_sources(self) -> None:
        detector = StaticRuleDetector(
            rules=[
                PrivacyReplacementRule(
                    id="r1",
                    before="shop.disney.com",
                    after="something.example.com",
                    match_type=PrivacyMatchType.SUBSTRING,
                    case_sensitive=False,
                    whole_word=False,
                )
            ]
        )
        self.assertEqual(detector.detect("ignored"), ["shop.disney.com"])

    def test_ner_detector_is_safe_placeholder(self) -> None:
        detector = NerDetector()
        self.assertEqual(detector.detect("anything"), [])


if __name__ == "__main__":
    unittest.main()
