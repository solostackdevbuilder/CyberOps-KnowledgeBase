"""
Privacy replacement utilities for sanitizing LLM payloads and restoring output.
"""
from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.services.privacy_alias_vault import PrivacyAliasVault
from app.core.storage.settings_store import SettingsStore
from app.models_settings import (
    EntityGroup,
    PrivacyMatchType,
    PrivacyReplacementRule,
    SensitiveKeywordRule,
    SensitiveRegexRule,
)

DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
    re.IGNORECASE,
)


class PrivacyLeakBlockedError(RuntimeError):
    """Raised when strict privacy mode detects an outbound leak."""


@dataclass
class CompiledReplacementRule:
    rule_id: str
    before: str
    after: str
    sanitize_pattern: re.Pattern[str]
    restore_pattern: re.Pattern[str]


@dataclass
class CompiledRegexRule:
    rule_id: str
    pattern: re.Pattern[str]
    replacement_label: str


@dataclass
class PrivacyTransformResult:
    text: str
    applied_rule_ids: list[str]


class RuleDetector(ABC):
    @abstractmethod
    def detect(self, text: str) -> list[str]:
        """Return candidate sensitive tokens from text."""


class StaticRuleDetector(RuleDetector):
    def __init__(self, rules: list[PrivacyReplacementRule], groups: list[EntityGroup] | None = None):
        self.rules = rules
        self.groups = groups or []

    def detect(self, text: str) -> list[str]:
        del text
        values = [rule.before for rule in self.rules]
        for group in self.groups:
            values.append(group.seed_name)
            values.extend(group.associated_terms)
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.casefold()
            if key in seen:
                continue
            deduped.append(value)
            seen.add(key)
        return deduped


class NerDetector(RuleDetector):
    def detect(self, text: str) -> list[str]:
        del text
        return []


def _make_pattern(source: str, whole_word: bool, case_sensitive: bool) -> re.Pattern[str]:
    escaped = re.escape(source)
    if whole_word:
        escaped = rf"\b{escaped}\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(escaped, flags)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "group"


def _compile_rules(rules: list[PrivacyReplacementRule]) -> list[CompiledReplacementRule]:
    ordered_rules = sorted(rules, key=lambda rule: len(rule.before), reverse=True)
    compiled: list[CompiledReplacementRule] = []
    for rule in ordered_rules:
        if rule.match_type == PrivacyMatchType.EXACT:
            sanitize_whole_word = True
            restore_whole_word = True
        else:
            sanitize_whole_word = rule.whole_word
            restore_whole_word = rule.whole_word

        compiled.append(
            CompiledReplacementRule(
                rule_id=rule.id,
                before=rule.before,
                after=rule.after,
                sanitize_pattern=_make_pattern(
                    rule.before,
                    whole_word=sanitize_whole_word,
                    case_sensitive=rule.case_sensitive,
                ),
                restore_pattern=_make_pattern(
                    rule.after,
                    whole_word=restore_whole_word,
                    case_sensitive=rule.case_sensitive,
                ),
            )
        )
    return compiled


class PrivacyTransformService:
    """Applies privacy replacements and strict domain aliasing around LLM boundaries."""

    def __init__(self, settings_store: SettingsStore | None = None):
        self.settings_store = settings_store or SettingsStore()
        self.alias_vault = PrivacyAliasVault()
        self._cached_rules: list[CompiledReplacementRule] = []
        self._cached_value_rule_ids: set[str] = set()
        self._cached_regex_rules: list[CompiledRegexRule] = []
        self._cached_protected_domain_terms: list[str] = []
        self._cached_settings: Any = None
        self._cache_until = 0.0
        self._runtime_token_map: dict[str, str] = {}
        self._runtime_counter = 0

    def _build_entity_rules(self, groups: list[EntityGroup]) -> list[PrivacyReplacementRule]:
        entity_rules: list[PrivacyReplacementRule] = []
        for group in groups:
            if not group.enabled:
                continue
            prefix = _slugify(group.name or group.seed_name)
            terms = [group.seed_name] + group.associated_terms
            for index, term in enumerate(terms, start=1):
                cleaned = term.strip()
                if not cleaned:
                    continue
                entity_rules.append(
                    PrivacyReplacementRule(
                        id=f"entity-{group.id}-{index}",
                        before=cleaned,
                        after=f"org_{prefix}_term_{index:03d}",
                        match_type=PrivacyMatchType.SUBSTRING,
                        case_sensitive=False,
                        whole_word=True,
                    )
                )
        return entity_rules

    def _build_keyword_rules(self, rules: list[SensitiveKeywordRule]) -> list[PrivacyReplacementRule]:
        keyword_rules: list[PrivacyReplacementRule] = []
        for rule in rules:
            if not rule.enabled:
                continue
            keyword_rules.append(
                PrivacyReplacementRule(
                    id=f"sensitive-kw-{rule.id}",
                    before=rule.keyword,
                    after=rule.replacement,
                    match_type=PrivacyMatchType.SUBSTRING,
                    case_sensitive=rule.case_sensitive,
                    whole_word=False,
                )
            )
        return keyword_rules

    def _build_regex_rules(self, rules: list[SensitiveRegexRule]) -> list[CompiledRegexRule]:
        compiled: list[CompiledRegexRule] = []
        for rule in rules:
            if not rule.enabled:
                continue
            compiled.append(
                CompiledRegexRule(
                    rule_id=f"sensitive-rx-{rule.id}",
                    pattern=re.compile(rule.pattern),
                    replacement_label=rule.replacement,
                )
            )
        return compiled

    def _dedupe_rules(self, rules: list[PrivacyReplacementRule]) -> list[PrivacyReplacementRule]:
        deduped: list[PrivacyReplacementRule] = []
        seen: set[str] = set()
        for rule in rules:
            key = rule.before.casefold()
            if key in seen:
                continue
            deduped.append(rule)
            seen.add(key)
        return deduped

    @staticmethod
    def _extract_domains(text: str) -> list[str]:
        return list({match.group(0).lower() for match in DOMAIN_PATTERN.finditer(text or "")})

    @staticmethod
    def _normalize_domain_term(term: str) -> str:
        value = term.strip().lower()
        if value.startswith("*."):
            value = value[2:]
        return value

    def _build_protected_domain_terms(
        self,
        manual_rules: list[PrivacyReplacementRule],
        groups: list[EntityGroup],
    ) -> list[str]:
        terms: list[str] = []
        for rule in manual_rules:
            if "." in rule.before:
                terms.append(self._normalize_domain_term(rule.before))
        for group in groups:
            if not group.enabled:
                continue
            terms.append(self._normalize_domain_term(group.seed_name))
            terms.extend(self._normalize_domain_term(term) for term in group.associated_terms)

        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            if not term:
                continue
            if term in seen:
                continue
            deduped.append(term)
            seen.add(term)
        return deduped

    async def _apply_domain_aliasing(
        self,
        text: str,
        protected_terms: list[str],
        alias_suffix: str,
    ) -> tuple[str, list[str]]:
        transformed = text
        applied_rule_ids: list[str] = []
        for domain in self._extract_domains(text):
            if domain.endswith(alias_suffix):
                continue
            if not any(term in domain for term in protected_terms):
                continue
            alias_domain = await self.alias_vault.get_or_create_alias_domain(domain, alias_suffix)
            transformed, count = re.subn(
                rf"\b{re.escape(domain)}\b",
                alias_domain,
                transformed,
                flags=re.IGNORECASE,
            )
            if count > 0:
                applied_rule_ids.append(f"domain-alias:{domain}")
        return transformed, applied_rule_ids

    def _assert_no_domain_leaks(
        self,
        text: str,
        protected_terms: list[str],
        alias_suffix: str,
    ) -> None:
        for domain in self._extract_domains(text):
            if domain.endswith(alias_suffix):
                continue
            if any(term in domain for term in protected_terms):
                raise PrivacyLeakBlockedError(
                    f"Strict privacy mode blocked outbound request; protected domain leak detected: {domain}"
                )

    def _assert_no_value_leaks(
        self,
        text: str,
        rules: list[CompiledReplacementRule],
    ) -> None:
        # Substring check on the raw `before` literal catches leaks that the rule's own
        # whole-word or case-sensitive pattern may have skipped (e.g. "disney" leaking via
        # "disneyland" when the rule requires whole-word). strict_privacy_mode promises
        # no protected value on the wire; this is deliberately stricter than the rule's
        # own matcher.
        #
        # Mask known replacement tokens first: some `after` values embed the original term
        # (entity groups use `org_<slug>_term_NNN` where slug is derived from the seed name),
        # which would otherwise false-trigger the substring check.
        haystack = text.lower()
        for rule in self._cached_rules:
            after_literal = rule.after.lower()
            if after_literal and after_literal in haystack:
                haystack = haystack.replace(after_literal, " " * len(after_literal))
        for rule in rules:
            needle = rule.before.strip().lower()
            if needle and needle in haystack:
                raise PrivacyLeakBlockedError(
                    f"Strict privacy mode blocked outbound request; protected value leak detected: rule={rule.rule_id}"
                )

    async def _load_settings_and_rules(
        self,
    ) -> tuple[Any, list[CompiledReplacementRule], list[CompiledRegexRule], list[str]]:
        now = time.time()
        if now < self._cache_until:
            return (
                self._cached_settings,
                self._cached_rules,
                self._cached_regex_rules,
                self._cached_protected_domain_terms,
            )

        app_settings = await self.settings_store.load_settings()
        privacy = app_settings.privacy_replacements
        defaults = privacy.sensitive_defaults

        if not privacy.enabled:
            self._cached_settings = app_settings
            self._cached_rules = []
            self._cached_value_rule_ids = set()
            self._cached_regex_rules = []
            self._cached_protected_domain_terms = []
            self._cache_until = now + 5
            return (
                self._cached_settings,
                self._cached_rules,
                self._cached_regex_rules,
                self._cached_protected_domain_terms,
            )

        manual_rules = privacy.rules
        entity_rules = self._build_entity_rules(privacy.entity_groups)
        value_rules = self._dedupe_rules(manual_rules + entity_rules)
        keyword_rules = self._build_keyword_rules(defaults.keyword_rules) if defaults.enabled else []
        merged_rules = self._dedupe_rules(value_rules + keyword_rules)

        self._cached_settings = app_settings
        self._cached_rules = _compile_rules(merged_rules)
        self._cached_value_rule_ids = {rule.id for rule in value_rules}
        regex_compiled: list[CompiledRegexRule] = []
        if defaults.enabled:
            regex_compiled.extend(self._build_regex_rules(defaults.regex_rules))
        regex_compiled.extend(self._build_regex_rules(privacy.custom_regex_rules))
        self._cached_regex_rules = regex_compiled
        self._cached_protected_domain_terms = self._build_protected_domain_terms(
            manual_rules=manual_rules,
            groups=privacy.entity_groups,
        )
        self._cache_until = now + 5
        return (
            self._cached_settings,
            self._cached_rules,
            self._cached_regex_rules,
            self._cached_protected_domain_terms,
        )

    async def should_restore_output(self) -> bool:
        app_settings, _, _, _ = await self._load_settings_and_rules()
        return (
            app_settings.privacy_replacements.enabled
            and app_settings.privacy_replacements.restore_on_output
            and app_settings.privacy_replacements.apply_to_ai_output
        )

    def _next_runtime_token(self, prefix: str) -> str:
        self._runtime_counter += 1
        return f"[[PRIV_{prefix}_{self._runtime_counter:05d}]]"

    async def sanitize_for_llm(self, text: str, target: str = "context") -> PrivacyTransformResult:
        app_settings, rules, regex_rules, protected_domain_terms = await self._load_settings_and_rules()
        if (not rules and not regex_rules) or not text:
            return PrivacyTransformResult(text=text, applied_rule_ids=[])

        privacy = app_settings.privacy_replacements
        if target == "question" and not privacy.apply_to_question:
            return PrivacyTransformResult(text=text, applied_rule_ids=[])
        if target == "context" and not privacy.apply_to_context:
            return PrivacyTransformResult(text=text, applied_rule_ids=[])

        transformed = text
        applied_rule_ids: list[str] = []

        alias_cfg = privacy.domain_alias_config
        if alias_cfg.enabled and protected_domain_terms:
            transformed, alias_rule_ids = await self._apply_domain_aliasing(
                transformed,
                protected_terms=protected_domain_terms,
                alias_suffix=alias_cfg.alias_suffix,
            )
            applied_rule_ids.extend(alias_rule_ids)

        # Regex rules must run before substring/keyword rules so that value-extracting
        # patterns (e.g. `authorization:\s*bearer\s+<token>`) can match literal context
        # before keyword rules like `kw-authorization` replace that context with markers.
        for regex_rule in regex_rules:
            def _replace(match: re.Match[str]) -> str:
                original_value = match.group(0)
                token = self._next_runtime_token(regex_rule.rule_id.upper())
                self._runtime_token_map[token] = original_value
                return token

            transformed, count = regex_rule.pattern.subn(_replace, transformed)
            if count > 0:
                applied_rule_ids.append(regex_rule.rule_id)

        for rule in rules:
            updated, count = rule.sanitize_pattern.subn(rule.after, transformed)
            if count > 0:
                transformed = updated
                applied_rule_ids.append(rule.rule_id)

        if privacy.strict_privacy_mode:
            if alias_cfg.enabled and protected_domain_terms:
                self._assert_no_domain_leaks(
                    transformed,
                    protected_terms=protected_domain_terms,
                    alias_suffix=alias_cfg.alias_suffix,
                )
            value_rules = [rule for rule in rules if rule.rule_id in self._cached_value_rule_ids]
            self._assert_no_value_leaks(transformed, value_rules)

        return PrivacyTransformResult(text=transformed, applied_rule_ids=applied_rule_ids)

    async def restore_for_ui(self, text: str) -> PrivacyTransformResult:
        _, rules, _, _ = await self._load_settings_and_rules()
        if not text:
            return PrivacyTransformResult(text=text, applied_rule_ids=[])

        transformed = text
        applied_rule_ids: list[str] = []

        reverse_alias_map = await self.alias_vault.get_reverse_map()
        for alias, original in sorted(reverse_alias_map.items(), key=lambda item: len(item[0]), reverse=True):
            transformed, count = re.subn(
                rf"\b{re.escape(alias)}\b",
                original,
                transformed,
                flags=re.IGNORECASE,
            )
            if count > 0:
                applied_rule_ids.append(f"domain-restore:{alias}")

        consumed: list[str] = []
        for token, original in list(self._runtime_token_map.items()):
            if token in transformed:
                transformed = transformed.replace(token, original)
                consumed.append(token)
        for token in consumed:
            self._runtime_token_map.pop(token, None)

        for rule in rules:
            updated, count = rule.restore_pattern.subn(rule.before, transformed)
            if count > 0:
                transformed = updated
                applied_rule_ids.append(rule.rule_id)

        return PrivacyTransformResult(text=transformed, applied_rule_ids=applied_rule_ids)

    def clear_runtime_tokens(self) -> None:
        self._runtime_token_map.clear()
        self._runtime_counter = 0

    async def restore_structure_for_ui(self, payload: Any) -> Any:
        if isinstance(payload, str):
            return (await self.restore_for_ui(payload)).text
        if isinstance(payload, list):
            return [await self.restore_structure_for_ui(item) for item in payload]
        if isinstance(payload, dict):
            restored: dict[Any, Any] = {}
            for key, value in payload.items():
                restored[key] = await self.restore_structure_for_ui(value)
            return restored
        return payload
