import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, afterEach } from 'vitest'
import CompanySearch from '../CompanySearch'

const RESULTS = [
  { ticker: 'AAPL', name: 'Apple Inc.', cik: '0000320193' },
  { ticker: 'AAPLX', name: 'Apple Something', cik: '0000999999' },
]

function mockFetch(data) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    json: () => Promise.resolve({ results: data }),
  }))
}

function type(input, value) {
  fireEvent.change(input, { target: { value } })
}

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

describe('CompanySearch', () => {
  it('renders input with placeholder', () => {
    render(<CompanySearch onSelect={vi.fn()} placeholder="Search here…" />)
    expect(screen.getByPlaceholderText('Search here…')).toBeInTheDocument()
  })

  it('does not search for queries shorter than 2 chars', () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<CompanySearch onSelect={vi.fn()} />)
    type(screen.getByRole('textbox'), 'a')
    vi.advanceTimersByTime(400)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows suggestions after debounce fires', async () => {
    mockFetch(RESULTS)
    render(<CompanySearch onSelect={vi.fn()} />)
    type(screen.getByRole('textbox'), 'ap')
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument(), { timeout: 1000 })
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
  })

  it('calls onSelect and clears results when suggestion clicked', async () => {
    mockFetch(RESULTS)
    const onSelect = vi.fn()
    render(<CompanySearch onSelect={onSelect} />)
    type(screen.getByRole('textbox'), 'ap')
    await waitFor(() => screen.getByText('AAPL'), { timeout: 1000 })
    fireEvent.click(screen.getByText('AAPL'))
    expect(onSelect).toHaveBeenCalledWith(RESULTS[0])
    expect(screen.queryByText('Apple Something')).not.toBeInTheDocument()
  })

  it('selects first result on Enter key', async () => {
    mockFetch(RESULTS)
    const onSelect = vi.fn()
    render(<CompanySearch onSelect={onSelect} />)
    const input = screen.getByRole('textbox')
    type(input, 'ap')
    await waitFor(() => screen.getByText('AAPL'), { timeout: 1000 })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith(RESULTS[0])
  })

  it('clears suggestions on Escape key', async () => {
    mockFetch(RESULTS)
    render(<CompanySearch onSelect={vi.fn()} />)
    const input = screen.getByRole('textbox')
    type(input, 'ap')
    await waitFor(() => screen.getByText('AAPL'), { timeout: 1000 })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
  })

  it('shows no results when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    render(<CompanySearch onSelect={vi.fn()} />)
    type(screen.getByRole('textbox'), 'ap')
    await waitFor(() => expect(screen.queryByRole('list')).not.toBeInTheDocument(), { timeout: 1000 })
  })

  it('disables input when disabled prop set', () => {
    render(<CompanySearch onSelect={vi.fn()} disabled />)
    expect(screen.getByRole('textbox')).toBeDisabled()
  })
})
