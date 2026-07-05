import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

describe('test harness smoke', () => {
  it('renders a DOM node and exposes jest-dom matchers', () => {
    render(<div>hello vitest</div>)
    expect(screen.getByText('hello vitest')).toBeInTheDocument()
  })
})
