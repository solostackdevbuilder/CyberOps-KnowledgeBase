import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import SessionForm from './SessionForm'

// Mock the API module so the form can render in isolation.
const getSessionMock = vi.fn()
const getOperationsMock = vi.fn()
const updateSessionMock = vi.fn()
const createSessionMock = vi.fn()
const extractMetadataMock = vi.fn()

vi.mock('../services/api', () => ({
  getSession: (...args: unknown[]) => getSessionMock(...args),
  getOperations: (...args: unknown[]) => getOperationsMock(...args),
  updateSession: (...args: unknown[]) => updateSessionMock(...args),
  createSession: (...args: unknown[]) => createSessionMock(...args),
  extractMetadata: (...args: unknown[]) => extractMetadataMock(...args),
}))

function renderEditForm(sessionId = 'sess-1') {
  return render(
    <MemoryRouter initialEntries={[`/session/${sessionId}/edit`]}>
      <Routes>
        <Route path="/session/:id/edit" element={<SessionForm />} />
      </Routes>
    </MemoryRouter>,
  )
}


describe('SessionForm - edit mode', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('pre-fills form inputs from the loaded session', async () => {
    getOperationsMock.mockResolvedValue([
      { id: 'op-1', name: 'Op One' },
    ])
    getSessionMock.mockResolvedValue({
      id: 'sess-1',
      title: 'My Session',
      description: 'a test run',
      tags: ['recon', 'nmap'],
      terminal_content: '$ whoami\nroot',
      operation_id: 'op-1',
      operator_name: 'Operator One',
      target: ['10.0.0.1', '10.0.0.2'],
      tools: ['nmap', 'masscan'],
      findings: ['port 22 open', 'port 80 open'],
      primary_tool: 'nmap',
      documentation_time_minutes: 45,
    })

    renderEditForm()

    // Title populates from session.title.
    const title = await screen.findByLabelText(/title/i) as HTMLInputElement
    expect(title.value).toBe('My Session')

    // Tags appear joined with ", ".
    const tags = screen.getByLabelText(/tags/i) as HTMLInputElement
    expect(tags.value).toBe('recon, nmap')

    // Operator.
    const operator = screen.getByLabelText(/operator name/i) as HTMLInputElement
    expect(operator.value).toBe('Operator One')

    // Terminal content in the textarea.
    const terminal = screen.getByLabelText(/terminal content/i) as HTMLTextAreaElement
    expect(terminal.value).toBe('$ whoami\nroot')

    // In edit mode, the operation select is disabled (users can't move
    // a session to a different operation from this form).
    const op = screen.getByLabelText(/operation/i) as HTMLSelectElement
    expect(op).toBeDisabled()
    expect(op.value).toBe('op-1')
  })

  it('submits an update with edited values and navigates on success', async () => {
    getOperationsMock.mockResolvedValue([
      { id: 'op-1', name: 'Op One' },
    ])
    getSessionMock.mockResolvedValue({
      id: 'sess-1',
      title: 'Original',
      tags: [],
      terminal_content: 'initial',
      operation_id: 'op-1',
      operator_name: 'Operator One',
      target: [],
      tools: [],
      findings: [],
    })
    updateSessionMock.mockResolvedValue({ id: 'sess-1' })

    renderEditForm('sess-1')

    const title = await screen.findByLabelText(/title/i) as HTMLInputElement
    await userEvent.clear(title)
    await userEvent.type(title, 'Edited title')

    const submitBtn = screen.getByRole('button', { name: /update session/i })
    await userEvent.click(submitBtn)

    await waitFor(() => {
      expect(updateSessionMock).toHaveBeenCalledOnce()
    })
    const [calledId, payload] = updateSessionMock.mock.calls[0]
    expect(calledId).toBe('sess-1')
    expect(payload.title).toBe('Edited title')
    // Edit mode should skip extraction and go straight to save.
    expect(extractMetadataMock).not.toHaveBeenCalled()
  })

  it('surfaces an API error when loading the session fails', async () => {
    getOperationsMock.mockResolvedValue([])
    getSessionMock.mockRejectedValue({
      response: { data: { detail: 'Session not found' } },
    })

    renderEditForm('missing')

    await waitFor(() => {
      expect(screen.getByText(/session not found/i)).toBeInTheDocument()
    })
  })
})
