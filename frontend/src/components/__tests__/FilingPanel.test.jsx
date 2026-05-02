import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import axios from 'axios'
import FilingPanel from '../FilingPanel'

vi.mock('axios')

const FILING = {
  company_name: 'Apple Inc.',
  filing_type: '10-K',
  filed_date: '2023-11-03',
  chunk_count: 120,
}

const LLM_RESPONSE = {
  answer: 'The main risks are competition and supply chain issues.',
  model_used: 'claude-haiku-4-5',
  cost_usd: 0.0005,
  latency_ms: 350,
}

describe('FilingPanel', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows empty state when no ticker provided', () => {
    render(<FilingPanel ticker={null} companyName="" filingId={null} filing={null} fetchingFiling={false} />)
    expect(screen.getByText(/search for a company/i)).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId={null} filing={null} fetchingFiling />)
    expect(screen.getByText(/fetching sec edgar/i)).toBeInTheDocument()
  })

  it('renders filing metadata when filing is ready', () => {
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />)
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
    expect(screen.getByText('10-K')).toBeInTheDocument()
    expect(screen.getByText('2023-11-03')).toBeInTheDocument()
    expect(screen.getByText('120 chunks')).toBeInTheDocument()
  })

  it('shows sample questions when chat history is empty', () => {
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />)
    expect(screen.getByText(/what are the main risk factors/i)).toBeInTheDocument()
  })

  it('sends question and displays answer', async () => {
    axios.post.mockResolvedValue({ data: LLM_RESPONSE })
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />)
    const input = screen.getByPlaceholderText(/ask a question/i)
    await userEvent.type(input, 'What are the risks?')
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => expect(screen.getByText(LLM_RESPONSE.answer)).toBeInTheDocument())
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/api/chat'),
      { question: 'What are the risks?', ticker: 'AAPL' }
    )
  })

  it('shows error message on failed chat request', async () => {
    axios.post.mockRejectedValue({ response: { data: { detail: 'LLM unavailable' } } })
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />)
    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'What are the risks?')
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => expect(screen.getByText('LLM unavailable')).toBeInTheDocument())
  })

  it('submit button disabled when question is empty', () => {
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />)
    expect(screen.getByRole('button', { name: /ask/i })).toBeDisabled()
  })

  it('sends question when sample question clicked', async () => {
    axios.post.mockResolvedValue({ data: LLM_RESPONSE })
    render(<FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />)
    fireEvent.click(screen.getByText(/what are the main risk factors/i))
    await waitFor(() => expect(axios.post).toHaveBeenCalled())
  })

  it('clears history when filingId changes', async () => {
    axios.post.mockResolvedValue({ data: LLM_RESPONSE })
    const { rerender } = render(
      <FilingPanel ticker="AAPL" companyName="Apple Inc." filingId="aapl-123" filing={FILING} fetchingFiling={false} />
    )
    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'test')
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => expect(screen.getByText(LLM_RESPONSE.answer)).toBeInTheDocument())
    rerender(<FilingPanel ticker="MSFT" companyName="Microsoft" filingId="msft-456" filing={FILING} fetchingFiling={false} />)
    expect(screen.queryByText(LLM_RESPONSE.answer)).not.toBeInTheDocument()
  })
})
