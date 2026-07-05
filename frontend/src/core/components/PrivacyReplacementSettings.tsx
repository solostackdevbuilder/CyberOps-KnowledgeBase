import { useState } from 'react';
import {
  EyeOff,
  Plus,
  Trash2,
  Shield,
  Building2,
  Sparkles,
  Loader2,
  Info,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import type {
  Settings,
  PrivacyReplacementSettings as PrivacySettings,
  PrivacyReplacementRule,
  PrivacyMatchType,
  EntityGroup,
  SensitiveDefaultsConfig,
  SensitiveRegexRule,
} from '../types/settings';
import { suggestAssociations } from '../services/api';

interface PrivacyReplacementSettingsProps {
  settings: Settings;
  onChange: (settings: Settings) => void;
}

interface ToggleControlProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  title?: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}

function ToggleControl({ checked, onChange, label, title, icon, disabled }: ToggleControlProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-disabled={disabled}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`w-full flex items-center justify-between gap-3 text-left ${
        disabled ? 'opacity-50 cursor-not-allowed' : ''
      }`}
      title={title}
    >
      <span className="text-white font-medium flex items-center gap-2">
        {icon}
        {label}
      </span>
      <span
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-blue-600' : 'bg-gray-600'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </span>
    </button>
  );
}

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-4">
      <div>
        <h3 className="text-lg font-medium text-white">{title}</h3>
        {description ? <p className="text-sm text-gray-400 mt-1">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

const DEFAULT_RULE: Omit<PrivacyReplacementRule, 'id'> = {
  before: '',
  after: '',
  match_type: 'substring',
  case_sensitive: false,
  whole_word: false,
};

const DEFAULT_PRIVACY_SETTINGS: PrivacySettings = {
  enabled: true,
  restore_on_output: true,
  apply_to_question: true,
  apply_to_context: true,
  apply_to_ai_output: true,
  strict_privacy_mode: true,
  domain_alias_config: {
    enabled: true,
    alias_suffix: 'example.com',
    stable_scope: 'global',
  },
  rules: [],
  entity_groups: [],
  sensitive_defaults: {
    enabled: true,
    keyword_rules: [],
    regex_rules: [],
  },
  custom_regex_rules: [],
};

function createRuleId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `rule-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function PrivacyReplacementSettings({ settings, onChange }: PrivacyReplacementSettingsProps) {
  const [suggestingGroupId, setSuggestingGroupId] = useState<string | null>(null);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  // Per-group notice describing which LLM provider saw the seed name. The
  // suggest-associations backend cannot privacy-mask its own seed (that would
  // defeat the feature), so we surface the provider to the user.
  const [suggestionProviderByGroup, setSuggestionProviderByGroup] = useState<Record<string, string>>({});
  const raw = settings.privacy_replacements;
  const privacy: PrivacySettings = {
    ...DEFAULT_PRIVACY_SETTINGS,
    ...(raw || {}),
    enabled: raw?.enabled ?? DEFAULT_PRIVACY_SETTINGS.enabled,
    restore_on_output: raw?.restore_on_output ?? DEFAULT_PRIVACY_SETTINGS.restore_on_output,
    apply_to_question: raw?.apply_to_question ?? DEFAULT_PRIVACY_SETTINGS.apply_to_question,
    apply_to_context: raw?.apply_to_context ?? DEFAULT_PRIVACY_SETTINGS.apply_to_context,
    apply_to_ai_output: raw?.apply_to_ai_output ?? DEFAULT_PRIVACY_SETTINGS.apply_to_ai_output,
    strict_privacy_mode: raw?.strict_privacy_mode ?? DEFAULT_PRIVACY_SETTINGS.strict_privacy_mode,
    rules: raw?.rules ?? DEFAULT_PRIVACY_SETTINGS.rules,
    entity_groups: raw?.entity_groups ?? DEFAULT_PRIVACY_SETTINGS.entity_groups,
    domain_alias_config: {
      ...DEFAULT_PRIVACY_SETTINGS.domain_alias_config!,
      ...raw?.domain_alias_config,
      enabled: raw?.domain_alias_config?.enabled ?? DEFAULT_PRIVACY_SETTINGS.domain_alias_config!.enabled,
      alias_suffix:
        raw?.domain_alias_config?.alias_suffix ?? DEFAULT_PRIVACY_SETTINGS.domain_alias_config!.alias_suffix,
      stable_scope:
        raw?.domain_alias_config?.stable_scope ?? DEFAULT_PRIVACY_SETTINGS.domain_alias_config!.stable_scope,
    },
    custom_regex_rules: raw?.custom_regex_rules ?? DEFAULT_PRIVACY_SETTINGS.custom_regex_rules ?? [],
  };
  const entityGroups = privacy.entity_groups || [];
  const sensitiveDefaults: SensitiveDefaultsConfig = {
    ...DEFAULT_PRIVACY_SETTINGS.sensitive_defaults!,
    ...privacy.sensitive_defaults,
    enabled: privacy.sensitive_defaults?.enabled ?? DEFAULT_PRIVACY_SETTINGS.sensitive_defaults!.enabled,
    keyword_rules:
      privacy.sensitive_defaults?.keyword_rules ?? DEFAULT_PRIVACY_SETTINGS.sensitive_defaults!.keyword_rules,
    regex_rules:
      privacy.sensitive_defaults?.regex_rules ?? DEFAULT_PRIVACY_SETTINGS.sensitive_defaults!.regex_rules,
  };
  const domainAliasConfig = privacy.domain_alias_config ?? DEFAULT_PRIVACY_SETTINGS.domain_alias_config!;

  const updatePrivacy = (updates: Partial<PrivacySettings>) => {
    onChange({
      ...settings,
      privacy_replacements: {
        ...privacy,
        ...updates,
      },
    });
  };

  const updateRule = (ruleId: string, updates: Partial<PrivacyReplacementRule>) => {
    const updatedRules = privacy.rules.map((rule) =>
      rule.id === ruleId ? { ...rule, ...updates } : rule
    );
    updatePrivacy({ rules: updatedRules });
  };

  const addRule = () => {
    const nextRule: PrivacyReplacementRule = {
      id: createRuleId(),
      ...DEFAULT_RULE,
    };
    updatePrivacy({ rules: [...privacy.rules, nextRule] });
  };

  const removeRule = (ruleId: string) => {
    updatePrivacy({ rules: privacy.rules.filter((rule) => rule.id !== ruleId) });
  };

  const customRegexRules = privacy.custom_regex_rules ?? [];

  const updateCustomRegexRule = (ruleId: string, updates: Partial<SensitiveRegexRule>) => {
    updatePrivacy({
      custom_regex_rules: customRegexRules.map((rule) =>
        rule.id === ruleId ? { ...rule, ...updates } : rule
      ),
    });
  };

  const addCustomRegexRule = () => {
    const next: SensitiveRegexRule = {
      id: createRuleId(),
      name: 'Custom pattern',
      pattern: '',
      replacement: '[REDACTED]',
      severity: 'high',
      enabled: true,
    };
    updatePrivacy({ custom_regex_rules: [...customRegexRules, next] });
  };

  const removeCustomRegexRule = (ruleId: string) => {
    updatePrivacy({ custom_regex_rules: customRegexRules.filter((r) => r.id !== ruleId) });
  };

  const addEntityGroup = () => {
    const nextGroup: EntityGroup = {
      id: createRuleId(),
      name: '',
      seed_name: '',
      associated_terms: [],
      enabled: true,
      generation_source: 'manual',
    };
    updatePrivacy({ entity_groups: [...entityGroups, nextGroup] });
  };

  const updateEntityGroup = (groupId: string, updates: Partial<EntityGroup>) => {
    updatePrivacy({
      entity_groups: entityGroups.map((group) =>
        group.id === groupId ? { ...group, ...updates } : group
      ),
    });
  };

  const removeEntityGroup = (groupId: string) => {
    updatePrivacy({ entity_groups: entityGroups.filter((group) => group.id !== groupId) });
  };

  const addAssociatedTerm = (groupId: string, term: string) => {
    const cleaned = term.trim();
    if (!cleaned) return;
    const group = entityGroups.find((g) => g.id === groupId);
    if (!group) return;
    if (group.associated_terms.some((item) => item.toLowerCase() === cleaned.toLowerCase())) {
      return;
    }
    updateEntityGroup(groupId, { associated_terms: [...group.associated_terms, cleaned] });
  };

  const removeAssociatedTerm = (groupId: string, term: string) => {
    const group = entityGroups.find((g) => g.id === groupId);
    if (!group) return;
    updateEntityGroup(groupId, {
      associated_terms: group.associated_terms.filter((item) => item !== term),
    });
  };

  const handleSuggestAssociations = async (group: EntityGroup) => {
    if (!group.seed_name.trim()) return;
    setSuggestingGroupId(group.id);
    try {
      const result = await suggestAssociations(group.seed_name, 20);
      if (result.success) {
        const existing = new Set(group.associated_terms.map((item) => item.toLowerCase()));
        const merged = [
          ...group.associated_terms,
          ...result.suggestions.filter((item) => !existing.has(item.toLowerCase())),
        ];
        updateEntityGroup(group.id, {
          associated_terms: merged,
          generation_source: 'external_ai',
          generated_at: new Date().toISOString(),
        });
      }
      if (result.provider_used) {
        setSuggestionProviderByGroup((prev) => ({
          ...prev,
          [group.id]: result.provider_used as string,
        }));
      }
    } finally {
      setSuggestingGroupId(null);
    }
  };

  const toggleSensitiveKeywordRule = (ruleId: string, enabled: boolean) => {
    updatePrivacy({
      sensitive_defaults: {
        ...sensitiveDefaults,
        keyword_rules: sensitiveDefaults.keyword_rules.map((rule) =>
          rule.id === ruleId ? { ...rule, enabled } : rule
        ),
      },
    });
  };

  const toggleSensitiveRegexRule = (ruleId: string, enabled: boolean) => {
    updatePrivacy({
      sensitive_defaults: {
        ...sensitiveDefaults,
        regex_rules: sensitiveDefaults.regex_rules.map((rule) =>
          rule.id === ruleId ? { ...rule, enabled } : rule
        ),
      },
    });
  };

  const normalizedSources = new Set<string>();
  const duplicateRuleIds = new Set<string>();
  privacy.rules.forEach((rule) => {
    const key = rule.before.trim().toLowerCase();
    if (!key) {
      return;
    }
    if (normalizedSources.has(key)) {
      duplicateRuleIds.add(rule.id);
      return;
    }
    normalizedSources.add(key);
  });

  const protectionOn = privacy.enabled;
  const restoreOn = privacy.restore_on_output ?? true;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white mb-2 flex items-center">
          <Shield className="h-6 w-6 mr-2" />
          Privacy Replacement Rules
        </h2>
        <p className="text-gray-400">
          Sensitive text is masked on this machine before it is sent to an AI provider. When restore is on, CyberOps
          maps placeholders and aliases back so you see the real values. Coverage depends on the rules and terms you
          configure-not every variant is caught automatically.
        </p>
      </div>

      <SettingsSection
        title="Master control, display, and safety"
        description="Turn the whole pipeline on or off, control what you see in the app, and block requests that would leak real domains."
      >
        <ToggleControl
          checked={privacy.enabled}
          onChange={(checked) => updatePrivacy({ enabled: checked })}
          label="Protect sensitive data before AI"
          title="When enabled, sensitive values are masked before AI calls and can be restored for display in CyberOps."
          icon={<Info className="h-4 w-4 text-gray-400" />}
        />
        <p className="text-xs text-gray-400 ml-1">
          <span className="text-gray-300">Recommended: on</span> for typical use.
          {protectionOn ? (
            <span> Protection is active; outbound text is masked according to your rules.</span>
          ) : (
            <span> Protection is off; raw values may be sent to external AI if you continue.</span>
          )}
        </p>

        <button
          type="button"
          onClick={() => setHowItWorksOpen((o) => !o)}
          className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300"
        >
          {howItWorksOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          How these options work together
        </button>
        {howItWorksOpen ? (
          <div className="text-sm text-gray-400 space-y-2 pl-1 border-l-2 border-gray-600 ml-1 py-1">
            <p>
              While protection is on, CyberOps masks configured terms (and optionally rewrites real hostnames to random
              fake subdomains under your suffix) before anything is sent to an external AI.
            </p>
            <p>
              Use <span className="text-gray-300">entity groups</span>, the <span className="text-gray-300">rule list</span>,{' '}
              <span className="text-gray-300">built-in packs</span>, and <span className="text-gray-300">custom regex</span> to
              cover the exact words and shapes you care about. Compound brands and odd URLs may need explicit terms or patterns.
            </p>
            <p>
              <span className="text-gray-300">Restore</span> swaps placeholders back so you see real values in the UI.
              Turning restore off leaves masked or tokenized text visible.{' '}
              <span className="text-gray-300">Strict mode</span> blocks the outbound request if a protected domain would
              still appear in the payload after masking (only applies when domain rewriting is enabled).
            </p>
          </div>
        ) : null}

        <ToggleControl
          checked={privacy.restore_on_output}
          onChange={(checked) => updatePrivacy({ restore_on_output: checked })}
          label="Restore original values in output"
          title="When on, masked tokens and rewritten domains are swapped back for display in the app."
          icon={<EyeOff className="h-4 w-4" />}
          disabled={!protectionOn}
        />

        <div className="pl-4 border-l border-gray-700 space-y-3">
          <ToggleControl
            checked={privacy.apply_to_ai_output ?? true}
            onChange={(checked) => updatePrivacy({ apply_to_ai_output: checked })}
            label="Apply restoration to AI-generated text"
            title="When on, replacements are restored in model replies as well as the rest of the UI. Requires Restore original values."
            disabled={!protectionOn || !restoreOn}
          />
          <p className="text-xs text-gray-500 -mt-2">
            Off means you may still see placeholders inside AI responses even when other UI text is restored.
          </p>
        </div>

        <ToggleControl
          checked={privacy.strict_privacy_mode ?? true}
          onChange={(checked) => updatePrivacy({ strict_privacy_mode: checked })}
          label="Strict privacy mode (block outbound request if protected value leaks)"
          title="If domain rewriting is on and a protected domain would still appear in outbound text, the request is blocked."
          disabled={!protectionOn}
        />
      </SettingsSection>

      <SettingsSection
        title="Outbound masking"
        description="What gets transformed before it leaves CyberOps for an AI provider (server-side masking before the provider sees it)."
      >
        <div className={`space-y-3 pl-3 border-l-2 border-gray-600 ${!protectionOn ? 'opacity-60' : ''}`}>
          <p className="text-xs text-gray-500 -mt-1 mb-2">Applies only while protection is on.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ToggleControl
              checked={privacy.apply_to_question ?? true}
              onChange={(checked) => updatePrivacy({ apply_to_question: checked })}
              label="Apply to question text"
              disabled={!protectionOn}
            />
            <ToggleControl
              checked={privacy.apply_to_context ?? true}
              onChange={(checked) => updatePrivacy({ apply_to_context: checked })}
              label="Apply to context text"
              disabled={!protectionOn}
            />
          </div>
        </div>

        <div className={`space-y-2 pt-2 ${!protectionOn ? 'opacity-60' : ''}`}>
          <ToggleControl
            checked={domainAliasConfig.enabled}
            onChange={(checked) =>
              updatePrivacy({
                domain_alias_config: {
                  ...domainAliasConfig,
                  enabled: checked,
                },
              })
            }
            label="Rewrite real domains to fake subdomains"
            title="Hostnames that contain a protected fragment are rewritten to a random stable label under your suffix-not your brand as a subdomain."
            disabled={!protectionOn}
          />
          <p className="text-xs text-gray-400 ml-1">
            The suffix (for example <span className="text-gray-300">example.com</span>) is one shared fake zone. Seeds and terms do not become{' '}
            <span className="text-gray-300">brand.example.com</span>; each matched real host becomes something like{' '}
            <span className="text-gray-300">a1b2c3d4e5f6g7h8.example.com</span>. Protected host fragments come from manual rules whose &quot;before&quot; value
            looks like a domain (contains a dot) and from each group&apos;s seed plus every associated term. Those same terms also
            produce literal placeholders (for example <span className="text-gray-300">org_disney_term_001</span>) in plain text-separate from hostname rewriting.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-end">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-400">Replacement domain suffix</label>
              <input
                type="text"
                value={domainAliasConfig.alias_suffix}
                onChange={(event) =>
                  updatePrivacy({
                    domain_alias_config: {
                      ...domainAliasConfig,
                      alias_suffix: event.target.value,
                    },
                  })
                }
                placeholder="example.com"
                disabled={!protectionOn}
                title="Single suffix for generated fake hostnames, e.g. example.com"
                className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
            </div>
            <div className="space-y-1">
              <label
                className="text-xs font-medium text-gray-400"
                title="How stable the random subdomain label is across sessions (vault-backed mappings are persisted)."
              >
                Alias stability
              </label>
              <select
                value={domainAliasConfig.stable_scope}
                onChange={(event) =>
                  updatePrivacy({
                    domain_alias_config: {
                      ...domainAliasConfig,
                      stable_scope: event.target.value as 'global' | 'operation' | 'request',
                    },
                  })
                }
                disabled={!protectionOn}
                title="How alias labels are scoped (global vs operation vs request)."
                className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              >
                <option
                  value="global"
                  title="Same fake hostname for a given real domain over time (persisted alias vault)."
                >
                  Global stable alias
                </option>
                <option
                  value="operation"
                  title="Future: stable labels within one operation. Today stored like global."
                >
                  Per operation
                </option>
                <option
                  value="request"
                  title="Future: new random label each request. Today stored like global."
                >
                  Per request
                </option>
              </select>
              <p className="text-xs text-gray-500">
                The server currently persists one mapping per real domain in the alias vault for all three options;
                per-operation and per-request behavior is reserved for a future release. Prefer Global unless you are
                aligning with planned API semantics.
              </p>
            </div>
          </div>
        </div>

        <div className="pt-4 border-t border-gray-700 space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-base font-medium text-white flex items-center gap-2">
              <Building2 className="h-5 w-5" />
              Seeded Entity Groups
            </h4>
            <button
              type="button"
              onClick={addEntityGroup}
              className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center gap-2"
            >
              <Plus className="h-4 w-4" />
              Add Group
            </button>
          </div>

        {entityGroups.length === 0 ? (
          <div className="p-4 rounded-md border border-dashed border-gray-600 text-gray-400 text-sm space-y-3">
            <p>
              No entity groups yet. For example, name a group <span className="text-gray-300">ACME Corp</span>, set seed{' '}
              <span className="text-gray-300">Acme Industries</span> (or a domain you care about), then click{' '}
              <span className="text-gray-300">Suggest Associations</span> and review terms. Add every variant you need; whole-word
              matching can miss compound names unless they are listed.
            </p>
            <button
              type="button"
              onClick={addEntityGroup}
              className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors inline-flex items-center gap-2"
            >
              <Plus className="h-4 w-4" />
              Add Group
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {entityGroups.map((group) => (
              <div key={group.id} className="rounded-md border border-gray-700 bg-gray-900/50 p-4 space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <input
                    type="text"
                    value={group.name}
                    onChange={(event) => updateEntityGroup(group.id, { name: event.target.value })}
                    placeholder="Group name (for example Disney)"
                    className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    type="text"
                    value={group.seed_name}
                    onChange={(event) => updateEntityGroup(group.id, { seed_name: event.target.value })}
                    placeholder="Seed / anchor (suggestions + domain detection)"
                    className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => handleSuggestAssociations(group)}
                    disabled={suggestingGroupId === group.id || !group.seed_name.trim()}
                    className="px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md transition-colors disabled:opacity-50 flex items-center gap-2"
                  >
                    {suggestingGroupId === group.id ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Suggesting...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4" />
                        Suggest Associations
                      </>
                    )}
                  </button>

                  <label className="flex items-center gap-2 text-sm text-gray-300">
                    <input
                      type="checkbox"
                      checked={group.enabled}
                      onChange={(event) => updateEntityGroup(group.id, { enabled: event.target.checked })}
                      className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
                    />
                    Enabled
                  </label>

                  <button
                    type="button"
                    onClick={() => removeEntityGroup(group.id)}
                    className="px-3 py-2 bg-red-700 hover:bg-red-800 text-white rounded-md transition-colors flex items-center gap-2"
                  >
                    <Trash2 className="h-4 w-4" />
                    Remove Group
                  </button>
                </div>

                {suggestionProviderByGroup[group.id] && (
                  <p className="text-xs text-amber-300/90 bg-amber-900/20 border border-amber-900/40 rounded px-3 py-2">
                    The seed <span className="font-mono">{group.seed_name}</span> was sent
                    to <span className="font-semibold">{suggestionProviderByGroup[group.id]}</span> to
                    generate suggestions. Seeds cannot be masked (they are what the LLM needs to
                    reason about), so treat the seed as having left this machine.
                  </p>
                )}

                <div className="space-y-2">
                  <p className="text-sm text-gray-300">Associated terms</p>
                  <div className="flex flex-wrap gap-2">
                    {group.associated_terms.map((term) => (
                      <button
                        key={term}
                        type="button"
                        onClick={() => removeAssociatedTerm(group.id, term)}
                        className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                        title="Click to remove"
                      >
                        {term} ×
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Add term and press Enter"
                      className="flex-1 px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          addAssociatedTerm(group.id, event.currentTarget.value);
                          event.currentTarget.value = '';
                        }
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Built-in Sensitive Defaults"
        description="Curated keyword and regex rules loaded from the server. They only take effect while protection is on."
      >
        <label
          className={`flex items-center gap-2 text-sm text-gray-300 ${!protectionOn ? 'opacity-60' : ''}`}
        >
          <input
            type="checkbox"
            checked={sensitiveDefaults.enabled}
            onChange={(event) =>
              updatePrivacy({
                sensitive_defaults: {
                  ...sensitiveDefaults,
                  enabled: event.target.checked,
                },
              })
            }
            disabled={!protectionOn}
            className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
          />
          Enable built-in keyword + regex protections
        </label>

        <div className="rounded-md border border-gray-700 bg-gray-900/40 p-4 space-y-3">
          <p className="text-sm text-gray-300">Keyword rules ({sensitiveDefaults.keyword_rules.length})</p>
          <div className="max-h-40 overflow-y-auto space-y-2">
            {sensitiveDefaults.keyword_rules.map((rule) => (
              <label key={rule.id} className="flex items-center justify-between gap-3 text-sm text-gray-300">
                <span>{rule.name} ({rule.severity})</span>
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  onChange={(event) => toggleSensitiveKeywordRule(rule.id, event.target.checked)}
                  disabled={!protectionOn}
                  className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                />
              </label>
            ))}
          </div>
        </div>

        <div className="rounded-md border border-gray-700 bg-gray-900/40 p-4 space-y-3">
          <p className="text-sm text-gray-300">Regex rules ({sensitiveDefaults.regex_rules.length})</p>
          <div className="max-h-48 overflow-y-auto space-y-2">
            {sensitiveDefaults.regex_rules.map((rule) => (
              <label key={rule.id} className="flex items-center justify-between gap-3 text-sm text-gray-300">
                <span>{rule.name} ({rule.severity})</span>
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  onChange={(event) => toggleSensitiveRegexRule(rule.id, event.target.checked)}
                  disabled={!protectionOn}
                  className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                />
              </label>
            ))}
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Custom regex rules"
        description="Python-style regex patterns you control. When protection is on, matches are replaced with an internal token before the AI request, then restored for you. Use the rule list below for simple fixed strings."
      >
        <div className={`flex items-center justify-between ${!protectionOn ? 'opacity-60' : ''}`}>
          <p className="text-sm text-gray-400">
            Invalid patterns are rejected when you save settings. Built-in regex packs still run separately when enabled.
          </p>
          <button
            type="button"
            onClick={addCustomRegexRule}
            disabled={!protectionOn}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            Add regex rule
          </button>
        </div>

        {customRegexRules.length === 0 ? (
          <p className="text-sm text-gray-500">No custom regex rules. Add one to catch patterns literals cannot express.</p>
        ) : (
          <div className="space-y-3">
            {customRegexRules.map((rule) => {
              let patternError: string | null = null;
              if (rule.pattern.trim()) {
                try {
                  new RegExp(rule.pattern);
                } catch {
                  patternError = 'Invalid JavaScript regex (server uses Python; most simple patterns match)';
                }
              }
              return (
                <div key={rule.id} className="rounded-md border border-gray-700 bg-gray-900/50 p-4 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={rule.name}
                      onChange={(e) => updateCustomRegexRule(rule.id, { name: e.target.value })}
                      placeholder="Rule name"
                      disabled={!protectionOn}
                      className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                    />
                    <select
                      value={rule.severity}
                      onChange={(e) =>
                        updateCustomRegexRule(rule.id, { severity: e.target.value as SensitiveRegexRule['severity'] })
                      }
                      disabled={!protectionOn}
                      className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                    >
                      <option value="critical">critical</option>
                      <option value="high">high</option>
                      <option value="medium">medium</option>
                    </select>
                  </div>
                  <textarea
                    value={rule.pattern}
                    onChange={(e) => updateCustomRegexRule(rule.id, { pattern: e.target.value })}
                    placeholder="Regular expression (Python re syntax)"
                    disabled={!protectionOn}
                    rows={2}
                    className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 font-mono text-sm"
                  />
                  {patternError ? <p className="text-xs text-amber-300">{patternError}</p> : null}
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-sm text-gray-300">
                      <input
                        type="checkbox"
                        checked={rule.enabled}
                        onChange={(e) => updateCustomRegexRule(rule.id, { enabled: e.target.checked })}
                        disabled={!protectionOn}
                        className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
                      />
                      Enabled
                    </label>
                    <button
                      type="button"
                      onClick={() => removeCustomRegexRule(rule.id)}
                      className="px-3 py-2 bg-red-700 hover:bg-red-800 text-white rounded-md transition-colors flex items-center gap-2"
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SettingsSection>


      <SettingsSection
        title="Rule list"
        description="Explicit find-and-replace style rules in addition to entity groups and built-in defaults."
      >
        <div className="flex items-center justify-between -mt-2">
          <span className="text-sm text-gray-400">Custom replacements</span>
          <button
            type="button"
            onClick={addRule}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Add Rule
          </button>
        </div>

        {privacy.rules.length === 0 ? (
          <div className="p-4 rounded-md border border-dashed border-gray-600 text-gray-400 text-sm space-y-3">
            <p>
              No rules yet. Add your first replacement rule, for example{' '}
              <span className="text-gray-300">shop.disney.com</span> →{' '}
              <span className="text-gray-300">something.example.com</span>.
            </p>
            <button
              type="button"
              onClick={addRule}
              className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors inline-flex items-center gap-2"
            >
              <Plus className="h-4 w-4" />
              Add Rule
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {privacy.rules.map((rule) => {
              const hasEmptyFields = !rule.before.trim() || !rule.after.trim();
              const hasDuplicateSource = duplicateRuleIds.has(rule.id);
              return (
                <div key={rule.id} className="rounded-md border border-gray-700 bg-gray-900/50 p-4 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={rule.before}
                      onChange={(event) => updateRule(rule.id, { before: event.target.value })}
                      placeholder="Before (sensitive value)"
                      className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <input
                      type="text"
                      value={rule.after}
                      onChange={(event) => updateRule(rule.id, { after: event.target.value })}
                      placeholder="After (safe replacement)"
                      className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-center">
                    <select
                      value={rule.match_type}
                      onChange={(event) =>
                        updateRule(rule.id, { match_type: event.target.value as PrivacyMatchType })
                      }
                      className="px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="substring">Substring</option>
                      <option value="exact">Exact</option>
                    </select>

                    <label className="flex items-center gap-2 text-sm text-gray-300">
                      <input
                        type="checkbox"
                        checked={rule.case_sensitive}
                        onChange={(event) => updateRule(rule.id, { case_sensitive: event.target.checked })}
                        className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
                      />
                      Case sensitive
                    </label>

                    <label className="flex items-center gap-2 text-sm text-gray-300">
                      <input
                        type="checkbox"
                        checked={rule.whole_word}
                        onChange={(event) => updateRule(rule.id, { whole_word: event.target.checked })}
                        className="rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
                      />
                      Whole word
                    </label>

                    <button
                      type="button"
                      onClick={() => removeRule(rule.id)}
                      className="px-3 py-2 bg-red-700 hover:bg-red-800 text-white rounded-md transition-colors flex items-center justify-center gap-2"
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </button>
                  </div>

                  {(hasEmptyFields || hasDuplicateSource) && (
                    <div className="text-sm text-amber-300">
                      {hasEmptyFields && <div>Before and After values are required.</div>}
                      {hasDuplicateSource && <div>Duplicate source values are not allowed.</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </SettingsSection>
    </div>
  );
}
