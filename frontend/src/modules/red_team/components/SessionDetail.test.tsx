import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import SessionDetail from './SessionDetail'

// SessionDetail is the operator's primary read surface - every session
// drill-down lands here. Previously untested. These smoke tests cover
// mount (fetch fires), the header-card content render path, the error
// branch, and the empty-screenshots branch. Deeper interactions
// (delete, upload, tab switch, extraction retry) layer on top.

const getSessionMock = vi.fn()
const getOperationMock = vi.fn()
const deleteSessionMock = vi.fn()
const retryExtractionMock = vi.fn()
const reprocessAllScreenshotsMock = vi.fn()
const getScreenshotUrlMock = vi.fn((sessionId: string, filename: string) => `/fake/${sessionId}/${filename}`)

vi.mock('../services/api', () => ({
  getSession: (...args: unknown[]) => getSessionMock(...args),
  getOperation: (...args: unknown[]) => getOperationMock(...args),
  deleteSession: (...args: unknown[]) => deleteSessionMock(...args),
  retryExtraction: (...args: unknown[]) => retryExtractionMock(...args),
  reprocessAllScreenshots: (...args: unknown[]) => reprocessAllScreenshotsMock(...args),
  getScreenshotUrl: (...args: [string, string]) => getScreenshotUrlMock(...args),
}))

// Heavy children stubbed - they have (or will have) their own tests.
vi.mock('./ScreenshotUpload', () => ({
  default: () => <div data-testid="screenshot-upload" />,
}))
vi.mock('./ExtractionResult', () => ({
  default: () => <div data-testid="extraction-result" />,
}))
vi.mock('./FAATab', () => ({
  default: () => <div data-testid="faa-tab">FAA items</div>,
}))
vi.mock('../../../components/TerminalViewer', () => ({
  default: () => <div data-testid="terminal-viewer" />,
}))


function renderDetail(id = 'sess-1') {
  return render(
    <MemoryRouter initialEntries={[`/session/${id}`]}>
      <Routes>
        <Route path="/session/:id" element={<SessionDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}


function baseSession(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sess-1',
    title: 'Initial recon',
    description: 'scanned the /24 and caught two web apps',
    tags: ['recon', 'nmap'],
    operation_id: 'op-1',
    operator_name: 'Operator One',
    terminal_content: '$ nmap -sV 10.0.0.0/24',
    target: ['10.0.0.1', '10.0.0.2'],
    tools: ['nmap'],
    findings: ['OpenSSH 8.2 on port 22', 'nginx 1.18 on port 80'],
    screenshots: [],
    screenshot_extractions: [],
    created_at: '2026-04-10T10:00:00Z',
    updated_at: '2026-04-10T11:30:00Z',
    ...overrides,
  }
}


describe('SessionDetail', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('fetches the session on mount', async () => {
    getSessionMock.mockResolvedValue(baseSession())
    getOperationMock.mockResolvedValue({ id: 'op-1', name: 'Op One' })

    renderDetail()

    await waitFor(() => {
      expect(getSessionMock).toHaveBeenCalledWith('sess-1')
      expect(getOperationMock).toHaveBeenCalledWith('op-1')
    })
  })

  it('renders the session header with title, operator, and operation', async () => {
    getSessionMock.mockResolvedValue(baseSession())
    getOperationMock.mockResolvedValue({ id: 'op-1', name: 'Op One' })

    renderDetail()

    expect(await screen.findByText('Initial recon')).toBeInTheDocument()
    expect(screen.getByText('Operator One')).toBeInTheDocument()
    // Operation name appears as a navigable link in the header.
    expect(screen.getByText('Op One')).toBeInTheDocument()
  })

  it('renders targets, tools, and findings from session metadata', async () => {
    getSessionMock.mockResolvedValue(baseSession())
    getOperationMock.mockResolvedValue({ id: 'op-1', name: 'Op One' })

    renderDetail()

    await screen.findByText('Initial recon')
    expect(screen.getByText('10.0.0.1')).toBeInTheDocument()
    expect(screen.getByText('10.0.0.2')).toBeInTheDocument()
    // "nmap" appears in both tools and tags; assert at least one render.
    expect(screen.getAllByText('nmap').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/OpenSSH 8\.2/)).toBeInTheDocument()
  })

  it('defaults to the FAA tab and mounts FAATab', async () => {
    getSessionMock.mockResolvedValue(baseSession())
    getOperationMock.mockResolvedValue({ id: 'op-1', name: 'Op One' })

    renderDetail()

    expect(await screen.findByTestId('faa-tab')).toBeInTheDocument()
    // Terminal tab content is not mounted until its button is clicked.
    expect(screen.queryByTestId('terminal-viewer')).not.toBeInTheDocument()
  })

  it('renders "No screenshots yet" in the screenshots tab when empty', async () => {
    getSessionMock.mockResolvedValue(baseSession({ screenshots: [] }))
    getOperationMock.mockResolvedValue({ id: 'op-1', name: 'Op One' })

    const { getByRole } = renderDetail()
    await screen.findByText('Initial recon')

    // Switch to the Screenshots tab (it's titled "Screenshots (N)").
    const screenshotTab = getByRole('button', { name: /screenshots \(0\)/i })
    screenshotTab.click()

    expect(await screen.findByText(/no screenshots yet/i)).toBeInTheDocument()
  })

  it('surfaces an error when the session fetch fails', async () => {
    getSessionMock.mockRejectedValue({
      response: { data: { detail: 'Session not found' } },
    })
    getOperationMock.mockResolvedValue(null)

    renderDetail('sess-missing')

    await waitFor(() => {
      expect(screen.getByText(/session not found/i)).toBeInTheDocument()
    })
  })
})
