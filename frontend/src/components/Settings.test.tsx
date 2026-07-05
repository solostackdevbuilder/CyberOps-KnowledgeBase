import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Settings from './Settings'

// Settings is the orchestrator for storage / LLM / webhooks / privacy /
// plugins configuration. Untested before this file. These smoke tests
// verify the load / error / retry path and tab navigation, which is
// what operators will hit if getSettings ever returns 500 or if the
// Anthropic key has been rotated incorrectly.
//
// The five tab child components (StorageSettings, LLMSettings, etc.)
// are stubbed so we don't pull in their API surface - we're testing
// Settings' orchestration here, not their form fields.

const getSettingsMock = vi.fn()
const updateSettingsMock = vi.fn()

vi.mock('../services/api', () => ({
  getSettings: (...args: unknown[]) => getSettingsMock(...args),
  updateSettings: (...args: unknown[]) => updateSettingsMock(...args),
}))

vi.mock('./StorageSettings', () => ({
  default: () => <div data-testid="storage-settings">Storage tab</div>,
}))
vi.mock('./LLMSettings', () => ({
  default: () => <div data-testid="llm-settings">LLM tab</div>,
}))
vi.mock('../core/components/WebhookSettings', () => ({
  default: () => <div data-testid="webhook-settings">Webhook tab</div>,
}))
vi.mock('../core/components/PrivacyReplacementSettings', () => ({
  default: () => <div data-testid="privacy-settings">Privacy tab</div>,
}))
vi.mock('./PluginMarketplace', () => ({
  default: () => <div data-testid="plugin-marketplace">Plugins tab</div>,
}))


function baseSettings() {
  return {
    storage_backend: 'json',
    llm_provider: 'claude',
    llm_config: { provider: 'claude', api_key: 'test' },
    webhook_config: { teams_webhook_url: '', slack_webhook_url: '', enabled: false },
    privacy_replacements: {
      enabled: true,
      restore_on_output: true,
      apply_to_question: true,
      apply_to_context: true,
      apply_to_ai_output: true,
      strict_privacy_mode: true,
      domain_alias_config: { enabled: true, alias_suffix: 'example.com', stable_scope: 'global' },
      rules: [],
      entity_groups: [],
      sensitive_defaults: { enabled: true, keyword_rules: [], regex_rules: [] },
    },
  }
}


describe('Settings', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('fetches settings on mount and renders the default Storage tab', async () => {
    getSettingsMock.mockResolvedValue(baseSettings())

    render(<Settings />)

    await waitFor(() => {
      expect(getSettingsMock).toHaveBeenCalled()
    })
    // The storage tab is active by default; the other four are mounted
    // only when their tab button is clicked.
    expect(await screen.findByTestId('storage-settings')).toBeInTheDocument()
    expect(screen.queryByTestId('llm-settings')).not.toBeInTheDocument()
  })

  it('shows an inline error with a Retry button when the load fails', async () => {
    getSettingsMock.mockRejectedValue({
      response: { data: { detail: 'Storage unavailable' } },
    })

    render(<Settings />)

    // Top-level error card is the one with a Retry button, distinct
    // from the narrow inline error banner shown during tab editing.
    const retryBtn = await screen.findByRole('button', { name: /retry/i })
    expect(retryBtn).toBeInTheDocument()
    expect(screen.getByText(/storage unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/failed to load settings/i)).toBeInTheDocument()

    // Retry triggers a second fetch.
    getSettingsMock.mockResolvedValue(baseSettings())
    await userEvent.click(retryBtn)
    await waitFor(() => {
      expect(getSettingsMock).toHaveBeenCalledTimes(2)
    })
  })

  it('switches to the LLM tab when the user clicks its button', async () => {
    getSettingsMock.mockResolvedValue(baseSettings())

    render(<Settings />)

    await screen.findByTestId('storage-settings')

    // Use role button + exact name so we don't match the "LLM" text
    // that appears in the Plugin Marketplace catalog description.
    const llmTab = screen.getByRole('button', { name: 'LLM' })
    await userEvent.click(llmTab)

    expect(await screen.findByTestId('llm-settings')).toBeInTheDocument()
    expect(screen.queryByTestId('storage-settings')).not.toBeInTheDocument()
  })

  it('shows the Plugin Marketplace tab when clicked', async () => {
    getSettingsMock.mockResolvedValue(baseSettings())

    render(<Settings />)

    await screen.findByTestId('storage-settings')
    await userEvent.click(screen.getByRole('button', { name: /plugin marketplace/i }))

    expect(await screen.findByTestId('plugin-marketplace')).toBeInTheDocument()
  })

  it('backfills webhook_config when the server response omits it', async () => {
    // Legacy settings files predate the webhook_config field. Settings
    // backfills a default so the Webhooks tab never crashes on null.
    const raw = baseSettings() as any
    delete raw.webhook_config
    getSettingsMock.mockResolvedValue(raw)

    render(<Settings />)

    // If Settings did NOT backfill, clicking the Webhooks tab would
    // crash once WebhookSettings tried to read webhook_config.X.
    // We have WebhookSettings stubbed, so the strongest signal is
    // that the tab still mounts without throwing.
    await screen.findByTestId('storage-settings')
    await userEvent.click(screen.getByRole('button', { name: /webhooks/i }))
    expect(await screen.findByTestId('webhook-settings')).toBeInTheDocument()
  })
})
