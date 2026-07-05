import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import TimelineView from './TimelineView'

// TimelineView is the visualization page - operations timeline,
// network diagram, kill chain. Untested before this file. Smoke tests
// cover mount (both API calls fire), tab switching, the filter select,
// and the error branch on timeline fetch failure.
//
// The three chart components (TimelineChart, NetworkDiagram,
// KillChainVisualization) are stubbed so we test TimelineView's
// orchestration, not their internal rendering - which is D3/canvas-
// heavy and needs its own setup.

const getOperationsTimelineMock = vi.fn()
const getNetworkDiagramMock = vi.fn()
const getOperationsMock = vi.fn()

vi.mock('../services/api', () => ({
  getOperationsTimeline: (...args: unknown[]) => getOperationsTimelineMock(...args),
  getNetworkDiagram: (...args: unknown[]) => getNetworkDiagramMock(...args),
}))

vi.mock('../modules/red_team/services/api', () => ({
  getOperations: (...args: unknown[]) => getOperationsMock(...args),
}))

vi.mock('./TimelineChart', () => ({
  default: () => <div data-testid="timeline-chart" />,
}))
vi.mock('./NetworkDiagram', () => ({
  default: () => <div data-testid="network-diagram" />,
}))
vi.mock('./KillChainVisualization', () => ({
  default: () => <div data-testid="kill-chain" />,
}))


function timeline() {
  return {
    total_operations: 2,
    total_sessions: 5,
    operations: [],
  }
}

function network() {
  return { nodes: [], edges: [] }
}

function renderView() {
  return render(
    <MemoryRouter>
      <TimelineView />
    </MemoryRouter>,
  )
}


describe('TimelineView', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('fires all three data fetches on mount', async () => {
    getOperationsMock.mockResolvedValue([])
    getOperationsTimelineMock.mockResolvedValue(timeline())
    getNetworkDiagramMock.mockResolvedValue(network())

    renderView()

    await waitFor(() => {
      expect(getOperationsMock).toHaveBeenCalled()
      expect(getOperationsTimelineMock).toHaveBeenCalled()
      expect(getNetworkDiagramMock).toHaveBeenCalled()
    })
  })

  it('renders the page heading and the Timeline tab by default', async () => {
    getOperationsMock.mockResolvedValue([])
    getOperationsTimelineMock.mockResolvedValue(timeline())
    getNetworkDiagramMock.mockResolvedValue(network())

    renderView()

    expect(await screen.findByText(/timeline & visualization/i)).toBeInTheDocument()
    expect(await screen.findByTestId('timeline-chart')).toBeInTheDocument()
    expect(screen.queryByTestId('network-diagram')).not.toBeInTheDocument()
  })

  it('switches to the Network Diagram tab on click', async () => {
    getOperationsMock.mockResolvedValue([])
    getOperationsTimelineMock.mockResolvedValue(timeline())
    getNetworkDiagramMock.mockResolvedValue(network())

    renderView()
    await screen.findByTestId('timeline-chart')

    await userEvent.click(screen.getByRole('button', { name: /network diagram/i }))

    expect(await screen.findByTestId('network-diagram')).toBeInTheDocument()
    expect(screen.queryByTestId('timeline-chart')).not.toBeInTheDocument()
  })

  it('refiltering by operation re-triggers the timeline fetch', async () => {
    getOperationsMock.mockResolvedValue([
      { id: 'op-1', name: 'Op One' },
      { id: 'op-2', name: 'Op Two' },
    ])
    getOperationsTimelineMock.mockResolvedValue(timeline())
    getNetworkDiagramMock.mockResolvedValue(network())

    renderView()

    // Wait for initial fetch to settle.
    await waitFor(() => {
      expect(getOperationsTimelineMock).toHaveBeenCalledTimes(1)
    })

    const select = screen.getByRole('combobox')
    await userEvent.selectOptions(select, 'op-2')

    await waitFor(() => {
      expect(getOperationsTimelineMock).toHaveBeenCalledTimes(2)
    })
    expect(getOperationsTimelineMock.mock.calls[1][0]).toBe('op-2')
  })

  it('surfaces an error when the timeline fetch fails', async () => {
    getOperationsMock.mockResolvedValue([])
    getOperationsTimelineMock.mockRejectedValue({
      response: { data: { detail: 'Timeline service down' } },
    })
    getNetworkDiagramMock.mockResolvedValue(network())

    renderView()

    await waitFor(() => {
      expect(screen.getByText(/timeline service down/i)).toBeInTheDocument()
    })
  })
})
