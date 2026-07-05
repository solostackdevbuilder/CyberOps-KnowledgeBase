import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QueryInterface from './QueryInterface'

// QueryInterface is the core Q&A UI - every operator using the tool
// hits it. Untested before this file. Smoke tests verify the mount
// path (settings + operations fetched), the disabled-until-typed
// submit button, the submit-flow happy path, and the error surface.

const submitQueryMock = vi.fn()
const getOperationsSummaryMock = vi.fn()
const getSettingsMock = vi.fn()

vi.mock('../services/api', () => ({
  submitQuery: (...args: unknown[]) => submitQueryMock(...args),
  getOperationsSummary: (...args: unknown[]) => getOperationsSummaryMock(...args),
}))

vi.mock('../../../core/services/api', () => ({
  getSettings: (...args: unknown[]) => getSettingsMock(...args),
}))

// Stub the rich child components - they have their own test surface.
vi.mock('./OperationScopeSelector', () => ({
  default: () => <div data-testid="op-scope" />,
}))
vi.mock('./QueryHistory', () => ({
  default: () => <div data-testid="query-history" />,
}))
vi.mock('../../../core/components/query/AnswerCard', () => ({
  default: ({ answer }: { answer: string }) => <div data-testid="answer-card">{answer}</div>,
}))
vi.mock('../../../core/components/query/SourceCard', () => ({
  default: () => <div data-testid="source-card" />,
}))
vi.mock('../../../core/components/query/IOCDisplay', () => ({
  default: () => <div data-testid="ioc-display" />,
  // Real extractIOCs returns a shape with ips/domains/hashes arrays;
  // QueryInterface reads their .length to decide whether to render.
  extractIOCs: () => ({ ips: [], domains: [], hashes: [] }),
}))


function defaultSettings() {
  return {
    storage_backend: 'json',
    llm_provider: 'claude',
    llm_config: { provider: 'claude', api_key: 'k', model_name: 'claude-sonnet-4-5-20250929' },
    webhook_config: { enabled: false },
    privacy_replacements: { enabled: true },
  }
}


describe('QueryInterface', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('fetches settings and operations summary on mount', async () => {
    getSettingsMock.mockResolvedValue(defaultSettings())
    getOperationsSummaryMock.mockResolvedValue([])

    render(<QueryInterface />)

    await waitFor(() => {
      expect(getSettingsMock).toHaveBeenCalled()
      expect(getOperationsSummaryMock).toHaveBeenCalled()
    })
  })

  it('disables the Query button until text is entered', async () => {
    getSettingsMock.mockResolvedValue(defaultSettings())
    getOperationsSummaryMock.mockResolvedValue([])

    render(<QueryInterface />)

    const submitBtn = await screen.findByRole('button', { name: /^query$/i })
    expect(submitBtn).toBeDisabled()

    const textarea = screen.getByPlaceholderText(/enter your question/i)
    await userEvent.type(textarea, 'what was scanned last week?')

    await waitFor(() => {
      expect(submitBtn).not.toBeDisabled()
    })
  })

  it('submits the query and renders the answer on success', async () => {
    getSettingsMock.mockResolvedValue(defaultSettings())
    getOperationsSummaryMock.mockResolvedValue([])
    submitQueryMock.mockResolvedValue({
      answer: 'Three hosts responded on port 22.',
      relevant_sessions: [],
      confidence: 0.8,
      scope_used: { session_count: 3 },
      metadata: {},
    })

    render(<QueryInterface />)

    const textarea = await screen.findByPlaceholderText(/enter your question/i)
    await userEvent.type(textarea, 'which hosts are SSH-reachable?')
    await userEvent.click(screen.getByRole('button', { name: /^query$/i }))

    await waitFor(() => {
      expect(submitQueryMock).toHaveBeenCalledOnce()
    })
    expect(await screen.findByTestId('answer-card')).toHaveTextContent(
      /three hosts responded on port 22/i,
    )
  })

  it('surfaces an error banner when the query fails', async () => {
    getSettingsMock.mockResolvedValue(defaultSettings())
    getOperationsSummaryMock.mockResolvedValue([])
    submitQueryMock.mockRejectedValue({
      response: { data: { detail: 'LLM rate limited' } },
    })

    render(<QueryInterface />)

    const textarea = await screen.findByPlaceholderText(/enter your question/i)
    await userEvent.type(textarea, 'something')
    await userEvent.click(screen.getByRole('button', { name: /^query$/i }))

    await waitFor(() => {
      expect(screen.getByText(/llm rate limited/i)).toBeInTheDocument()
    })
  })

  it('shows the operations-load warning when the summary fetch fails', async () => {
    getSettingsMock.mockResolvedValue(defaultSettings())
    getOperationsSummaryMock.mockRejectedValue({
      response: { data: { detail: 'Storage unavailable' } },
    })

    render(<QueryInterface />)

    await waitFor(() => {
      // Warning text is "<detail>. Defaulting to \"All Operations\"."
      expect(screen.getByText(/storage unavailable/i)).toBeInTheDocument()
    })
  })
})
