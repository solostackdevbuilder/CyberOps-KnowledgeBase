import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ScreenshotUpload from './ScreenshotUpload'

vi.mock('../services/api', () => ({
  uploadScreenshot: vi.fn(async () => ({
    success: true,
    screenshot_path: 'fake.png',
    extraction: null,
  })),
}))

vi.mock('../../../core/services/api', () => ({
  getSettings: vi.fn(async () => ({
    llm_supports_vision: true,
  })),
}))

function renderWithRouter(sessionId = 's1') {
  return render(
    <MemoryRouter>
      <ScreenshotUpload sessionId={sessionId} onUploaded={() => {}} />
    </MemoryRouter>,
  )
}

function _fakeImageFile(name = 'test.png'): File {
  return new File(['x'], name, { type: 'image/png' })
}

function _dispatchPasteOnDocument(items: Array<{ kind: string; type: string; file: File | null }>) {
  const event = new Event('paste', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'clipboardData', {
    value: {
      items: items.map((it) => ({
        kind: it.kind,
        type: it.type,
        getAsFile: () => it.file,
      })),
    },
  })
  document.dispatchEvent(event)
}


describe('ScreenshotUpload - paste intake', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('accepts a pasted image and shows the "Pasted from clipboard" banner', async () => {
    renderWithRouter()
    // Wait for the dropzone to render.
    await screen.findByText(/drag and drop an image/i)

    _dispatchPasteOnDocument([
      { kind: 'file', type: 'image/png', file: _fakeImageFile('image.png') },
    ])

    await waitFor(() => {
      expect(screen.getByText(/pasted from clipboard/i)).toBeInTheDocument()
    })
  })

  it('ignores a paste while focus is inside an input', async () => {
    renderWithRouter()
    await screen.findByText(/drag and drop an image/i)

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'target', { value: input })
    Object.defineProperty(event, 'clipboardData', {
      value: {
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => _fakeImageFile(),
          },
        ],
      },
    })
    input.dispatchEvent(event)

    // Dropzone should still be visible since handleFileSelect was skipped.
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getByText(/drag and drop an image/i)).toBeInTheDocument()
    expect(screen.queryByText(/pasted from clipboard/i)).not.toBeInTheDocument()

    input.remove()
  })

  it('ignores a paste that carries only a plain-text item', async () => {
    renderWithRouter()
    await screen.findByText(/drag and drop an image/i)

    _dispatchPasteOnDocument([
      { kind: 'string', type: 'text/plain', file: null },
    ])

    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getByText(/drag and drop an image/i)).toBeInTheDocument()
  })
})


describe('ScreenshotUpload - drag and drop', () => {
  it('rejects a dropped non-image with a clear error', async () => {
    renderWithRouter()
    await screen.findByText(/drag and drop an image/i)

    const dropped = new File(['x'], 'doc.pdf', { type: 'application/pdf' })
    const dropEvent = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(dropEvent, 'dataTransfer', {
      value: {
        types: ['Files'],
        files: [dropped],
      },
    })
    document.dispatchEvent(dropEvent)

    await waitFor(() => {
      expect(screen.getByText(/please drop an image/i)).toBeInTheDocument()
    })
  })
})


describe('ScreenshotUpload - screen capture', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('surfaces an error when the browser lacks getDisplayMedia', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      value: {},
      configurable: true,
    })

    renderWithRouter()

    const captureBtn = await screen.findByRole('button', { name: /capture screen/i })
    captureBtn.click()

    await waitFor(() => {
      expect(screen.getByText(/not supported/i)).toBeInTheDocument()
    })
  })
})
