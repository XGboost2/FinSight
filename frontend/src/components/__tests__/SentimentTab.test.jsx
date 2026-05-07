import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import axios from 'axios'
import SentimentTab from '../tabs/SentimentTab'

vi.mock('axios')

const SENTIMENT = {
  ticker: 'AAPL',
  filing_id: 'abc123',
  score: 0.72,
  label: 'Positive',
  avg_positive: 0.65,
  avg_negative: 0.08,
  avg_neutral: 0.27,
  chunk_count: 12,
  top_sentences: [
    { text: 'Revenue increased significantly this quarter.', label: 'positive', score: 0.95 },
    { text: 'We face significant regulatory headwinds.', label: 'negative', score: 0.88 },
  ],
  model: 'ProsusAI/finbert',
  source: 'Item 7 — MD&A',
}

describe('SentimentTab', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows placeholder when no ticker', () => {
    render(<SentimentTab ticker={null} />)
    expect(screen.queryByText(/run analysis on the fundamentals tab/i)).toBeInTheDocument()
  })

  it('shows loading spinner while fetching', () => {
    axios.get.mockReturnValue(new Promise(() => {}))
    render(<SentimentTab ticker="AAPL" />)
    expect(screen.getByText(/running finbert/i)).toBeInTheDocument()
  })

  it('shows error message on failed fetch', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'No filing found.' } } })
    render(<SentimentTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('No filing found.')).toBeInTheDocument())
  })

  it('renders agent header with FinBERT badge', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    render(<SentimentTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('FinBERT')).toBeInTheDocument())
    expect(screen.getByText('Sentiment Analyst')).toBeInTheDocument()
  })

  it('shows overall score and label', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    render(<SentimentTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getAllByText('Positive').length).toBeGreaterThan(0))
    expect(screen.getByText('72')).toBeInTheDocument()
  })

  it('shows chunk count in source line', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    render(<SentimentTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText(/12 chunks/)).toBeInTheDocument())
  })

  it('renders class probability breakdown', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    render(<SentimentTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('Class Probabilities')).toBeInTheDocument())
    expect(screen.getByText('Negative')).toBeInTheDocument()
    expect(screen.getByText('Neutral')).toBeInTheDocument()
  })

  it('renders top polarised sentences', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    render(<SentimentTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText('Revenue increased significantly this quarter.')).toBeInTheDocument()
    )
    expect(screen.getByText('We face significant regulatory headwinds.')).toBeInTheDocument()
  })

  it('calls onStatusChange with done on success', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    const onStatusChange = vi.fn()
    render(<SentimentTab ticker="AAPL" onStatusChange={onStatusChange} />)
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith('done'))
  })

  it('calls onStatusChange with error on failure', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'err' } } })
    const onStatusChange = vi.fn()
    render(<SentimentTab ticker="AAPL" onStatusChange={onStatusChange} />)
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith('error'))
  })

  it('fetches from /sentiment endpoint', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    render(<SentimentTab ticker="NVDA" />)
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining('/api/companies/NVDA/sentiment')
    ))
  })

  it('re-fetches when ticker changes', async () => {
    axios.get.mockResolvedValue({ data: SENTIMENT })
    const { rerender } = render(<SentimentTab ticker="AAPL" />)
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1))
    rerender(<SentimentTab ticker="TSLA" />)
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2))
    expect(axios.get).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/companies/TSLA/sentiment')
    )
  })
})
