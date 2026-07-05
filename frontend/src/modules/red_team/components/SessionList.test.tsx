import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import SessionList from './SessionList'

// SessionList is the landing page operators see on every session-
// picker interaction. Untested before this file - these smoke tests
// cover the load path, the filter/search path, and the two states
// operators most often see (empty filter result, load failure).
//
// The full interaction surface (delete, quick-create, keyboard
// shortcuts, three view modes) is out of scope here; we verify the
// component mounts, fetches, filters, and errors gracefully. Deeper
// interaction tests layer on top.

const getSessionsMock = vi.fn()
const getOperationsMock = vi.fn()
const deleteSessionMock = vi.fn()

vi.mock('../services/api', () => ({
  getSessions: (...args: unknown[]) => getSessionsMock(...args),
  getOperations: (...args: unknown[]) => getOperationsMock(...args),
  deleteSession: (...args: unknown[]) => deleteSessionMock(...args),
}))

// QuickSessionCreate imports its own API chain; stub it to a trivial
// element so we don't pull in a second mock tree just to render the list.
vi.mock('../../../components/QuickSessionCreate', () => ({
  default: () => null,
}))

function renderList() {
  return render(
    <MemoryRouter>
      <SessionList />
    </MemoryRouter>,
  )
}

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sess-1',
    title: 'Recon against 10.0.0.0/24',
    description: 'initial scan',
    tags: ['recon', 'nmap'],
    operation_id: 'op-1',
    operator_name: 'Operator One',
    terminal_content: '$ nmap -sV 10.0.0.0/24',
    created_at: '2026-04-10T10:00:00Z',
    updated_at: '2026-04-10T10:00:00Z',
    screenshots: [],
    ...overrides,
  }
}


describe('SessionList', () => {
  afterEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('fetches sessions and operations on mount', async () => {
    getSessionsMock.mockResolvedValue([])
    getOperationsMock.mockResolvedValue([])

    renderList()

    await waitFor(() => {
      expect(getSessionsMock).toHaveBeenCalled()
      expect(getOperationsMock).toHaveBeenCalled()
    })
  })

  it('renders loaded session titles', async () => {
    getSessionsMock.mockResolvedValue([
      session({ id: 's1', title: 'First session' }),
      session({ id: 's2', title: 'Second session', operation_id: 'op-2' }),
    ])
    getOperationsMock.mockResolvedValue([
      { id: 'op-1', name: 'Op One' },
      { id: 'op-2', name: 'Op Two' },
    ])

    renderList()

    await waitFor(() => {
      expect(screen.getByText('First session')).toBeInTheDocument()
      expect(screen.getByText('Second session')).toBeInTheDocument()
    })
  })

  it('filters sessions by the search query (title match)', async () => {
    // Filter matches title/description/operator/tags/terminal_content;
    // override every field so the assertion turns purely on the title.
    getSessionsMock.mockResolvedValue([
      session({
        id: 's1',
        title: 'Bloodhound collection',
        description: 'AD enumeration',
        tags: ['ad', 'recon'],
        terminal_content: '$ SharpHound.exe',
      }),
      session({
        id: 's2',
        title: 'Port scan phase',
        description: 'nmap sweep',
        tags: ['nmap', 'recon'],
        terminal_content: '$ nmap -p-',
      }),
    ])
    getOperationsMock.mockResolvedValue([])

    renderList()

    await screen.findByText('Bloodhound collection')

    const searchBox = screen.getByPlaceholderText(/search sessions/i)
    await userEvent.type(searchBox, 'port scan')

    await waitFor(() => {
      expect(screen.queryByText('Bloodhound collection')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Port scan phase')).toBeInTheDocument()
  })

  it('shows the empty-results message when search matches nothing', async () => {
    getSessionsMock.mockResolvedValue([
      session({ id: 's1', title: 'Bloodhound' }),
    ])
    getOperationsMock.mockResolvedValue([])

    renderList()

    await screen.findByText('Bloodhound')

    const searchBox = screen.getByPlaceholderText(/search sessions/i)
    await userEvent.type(searchBox, 'xyz-no-match')

    await waitFor(() => {
      expect(screen.getByText(/no sessions match your filters/i)).toBeInTheDocument()
    })
  })

  it('surfaces an error message when the load fails', async () => {
    getSessionsMock.mockRejectedValue({
      response: { data: { detail: 'Storage unavailable' } },
    })
    getOperationsMock.mockResolvedValue([])

    renderList()

    await waitFor(() => {
      expect(screen.getByText(/storage unavailable/i)).toBeInTheDocument()
    })
  })
})
