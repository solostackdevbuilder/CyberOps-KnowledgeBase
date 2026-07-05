import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import BrowserExtensionPage from './BrowserExtensionPage'

// Mock fetch responses for /api/plugins/browser_extension endpoints.
// Tests substitute the implementation in beforeEach so each test has a
// fresh mock with a known state machine.

type HealthShape = {
  status: string
  plugin: string
  token_configured: boolean
  last_heartbeat: string | null
  captures_total: number
}

function installFetchMock(
  health: HealthShape,
  opts: { rotateFails?: boolean } = {},
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'

    if (url.endsWith('/health') && method === 'GET') {
      return new Response(JSON.stringify(health), { status: 200 })
    }
    if (url.endsWith('/token/rotate') && method === 'POST') {
      if (opts.rotateFails) {
        return new Response('boom', { status: 500 })
      }
      // Once rotated, the health endpoint should start reporting
      // token_configured=true on subsequent calls.
      health.token_configured = true
      return new Response(JSON.stringify({ token: 'test-token-abcdef123456' }), { status: 200 })
    }
    return new Response('not found', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}


describe('BrowserExtensionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders install steps and plugin heading', async () => {
    installFetchMock({
      status: 'ok',
      plugin: 'browser_extension',
      token_configured: false,
      last_heartbeat: null,
      captures_total: 0,
    })
    render(<BrowserExtensionPage />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Browser Extension')
    expect(screen.getByRole('heading', { name: 'Install' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Pairing token' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Status' })).toBeInTheDocument()

    // Download link points at the plugin's download endpoint.
    const downloadLink = screen.getByRole('link', { name: /download the extension/i })
    expect(downloadLink).toHaveAttribute('href', '/api/plugins/browser_extension/download')
  })

  it('loads health on mount and shows token_configured=No initially', async () => {
    installFetchMock({
      status: 'ok',
      plugin: 'browser_extension',
      token_configured: false,
      last_heartbeat: null,
      captures_total: 0,
    })
    render(<BrowserExtensionPage />)

    // "Generate token" button appears once health loads and says no token.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate token/i })).toBeInTheDocument()
    })
    expect(screen.getByText(/token configured/i).nextSibling?.textContent).toMatch(/no/i)
  })

  it('rotates token and reveals the copy flow', async () => {
    installFetchMock({
      status: 'ok',
      plugin: 'browser_extension',
      token_configured: false,
      last_heartbeat: null,
      captures_total: 0,
    })
    render(<BrowserExtensionPage />)

    const generateBtn = await screen.findByRole('button', { name: /generate token/i })
    await userEvent.click(generateBtn)

    // New token is revealed in the pairing card.
    await waitFor(() => {
      expect(screen.getByText('test-token-abcdef123456')).toBeInTheDocument()
    })
    expect(screen.getByText(/copy this now/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeInTheDocument()
  })

  it('prompts for confirmation before rotating an existing token', async () => {
    const confirmSpy = vi.fn(() => false)
    vi.stubGlobal('confirm', confirmSpy)

    const fetchMock = installFetchMock({
      status: 'ok',
      plugin: 'browser_extension',
      token_configured: true,
      last_heartbeat: '2026-04-19T00:00:00Z',
      captures_total: 3,
    })

    render(<BrowserExtensionPage />)
    const rotateBtn = await screen.findByRole('button', { name: /rotate token/i })
    await userEvent.click(rotateBtn)

    expect(confirmSpy).toHaveBeenCalledOnce()
    // User said "no" - no rotate call should have been fired.
    const calls = fetchMock.mock.calls
      .map((c) => `${(c[1] as RequestInit | undefined)?.method ?? 'GET'} ${c[0]}`)
    expect(calls.some((c) => c.includes('POST') && c.includes('/token/rotate'))).toBe(false)
  })

  it('copies the new token to the clipboard', async () => {
    const writeText = vi.fn(async () => {})
    // Defining the property preserves the real navigator while swapping
    // out clipboard.writeText - happy-dom's navigator doesn't spread well
    // through vi.stubGlobal.
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    installFetchMock({
      status: 'ok',
      plugin: 'browser_extension',
      token_configured: false,
      last_heartbeat: null,
      captures_total: 0,
    })

    render(<BrowserExtensionPage />)
    await userEvent.click(await screen.findByRole('button', { name: /generate token/i }))
    await userEvent.click(await screen.findByRole('button', { name: /^copy$/i }))

    // The visible behavior we care about: the token made it to the
    // clipboard. The "Copied" label flips back after 2s, so don't assert
    // on it (would either be flaky or require fake timers just for UX text).
    expect(writeText).toHaveBeenCalledWith('test-token-abcdef123456')
  })

  it('surfaces a network error from the rotate endpoint', async () => {
    installFetchMock(
      {
        status: 'ok',
        plugin: 'browser_extension',
        token_configured: false,
        last_heartbeat: null,
        captures_total: 0,
      },
      { rotateFails: true },
    )
    render(<BrowserExtensionPage />)

    await userEvent.click(await screen.findByRole('button', { name: /generate token/i }))

    await waitFor(() => {
      expect(screen.getByText(/HTTP 500/)).toBeInTheDocument()
    })
  })
})
