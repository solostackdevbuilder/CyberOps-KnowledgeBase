import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import PluginMarketplace from './PluginMarketplace'

// PluginMarketplace fetches /api/platform/manifest plus per-plugin /health
// endpoints. Smoke tests here verify the catalog renders and the component
// handles an empty-manifest response without crashing. Deep interaction
// testing (enable/disable, health polling) can be layered on top later.


function installFetchMock(installedIds: string[] = []) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.endsWith('/api/platform/manifest')) {
      const plugins = installedIds.map((id) => ({
        id,
        name: id,
        type: 'tool',
        description: `${id} plugin`,
        pages: [],
      }))
      return new Response(JSON.stringify({ plugins }), { status: 200 })
    }
    if (url.includes('/health')) {
      return new Response(
        JSON.stringify({ status: 'ok', plugin: url.split('/')[3] }),
        { status: 200 },
      )
    }
    return new Response(JSON.stringify({}), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}


describe('PluginMarketplace', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders the known-plugin catalog even when none are installed', async () => {
    installFetchMock([])
    render(<PluginMarketplace />)

    // Catalog entries are hardcoded in the component and should render
    // regardless of what /api/platform/manifest returns. Assert on the
    // curated names that ship with the app.
    await waitFor(() => {
      expect(screen.getByText(/hashcat password cracker/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/john the ripper/i)).toBeInTheDocument()
    expect(screen.getByText(/nmap scanner/i)).toBeInTheDocument()
    expect(screen.getByText(/remote servers/i)).toBeInTheDocument()
  })

  it('issues a manifest request on mount', async () => {
    const fetchMock = installFetchMock([])
    render(<PluginMarketplace />)

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.endsWith('/api/platform/manifest'))).toBe(true)
    })
  })

  it('survives a failing manifest call', async () => {
    // Network error on manifest should not tear down the component -
    // the static catalog still renders and the user can see what's
    // available even if live health data is unavailable.
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('network down')
    }))

    render(<PluginMarketplace />)

    await waitFor(() => {
      // The catalog entries come from a local constant, not the API,
      // so they must still render even when fetch throws.
      expect(screen.getByText(/hashcat password cracker/i)).toBeInTheDocument()
    })
  })
})
