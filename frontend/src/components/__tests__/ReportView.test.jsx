import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import axios from 'axios'
import ReportView from '../ReportView'

vi.mock('axios')

const REPORT = {
  ticker: 'AAPL',
  company_name: 'Apple Inc.',
  generated_at: '2026-01-15T10:00:00Z',
  company_overview: 'Apple designs consumer electronics and software.',
  trend_narrative: 'Revenue softened but margins expanded on services mix shift.',
  findings_table: [
    { category: 'Revenue', metric: 'Total Revenue', value: '$394.3B', yoy: '-2.8%', signal: 'caution', interpretation: 'Hardware demand weakened.' },
    { category: 'Profitability', metric: 'Gross Margin', value: '44.1%', yoy: '+0.8pp', signal: 'positive', interpretation: 'Services mix improving margins.' },
  ],
  risk_score: 0.34,
  risk_factors: ['Competition', 'Regulatory risk', 'Supply chain'],
  sentiment_score: 0.68,
  sentiment_label: 'Positive',
  verdict: 'Apple remains fundamentally strong with moderate risk.',
}

describe('ReportView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders nothing when no ticker', () => {
    const { container } = render(<ReportView ticker={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows ingesting state', () => {
    render(<ReportView ticker="AAPL" ingesting />)
    expect(screen.getByText(/fetching 10-k filing/i)).toBeInTheDocument()
  })

  it('shows generating state while loading', () => {
    axios.get.mockReturnValue(new Promise(() => {}))
    render(<ReportView ticker="AAPL" ingesting={false} />)
    expect(screen.getByText(/generating analysis report/i)).toBeInTheDocument()
  })

  it('renders company overview on success', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<ReportView ticker="AAPL" ingesting={false} />)
    await waitFor(() =>
      expect(screen.getByText(REPORT.company_overview)).toBeInTheDocument()
    )
  })

  it('renders ticker and company name in header', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<ReportView ticker="AAPL" ingesting={false} />)
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
  })

  it('renders findings table with all rows', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<ReportView ticker="AAPL" ingesting={false} />)
    await waitFor(() => expect(screen.getByText('$394.3B')).toBeInTheDocument())
    expect(screen.getByText('-2.8%')).toBeInTheDocument()
    expect(screen.getByText('44.1%')).toBeInTheDocument()
    expect(screen.getByText('Hardware demand weakened.')).toBeInTheDocument()
  })

  it('renders verdict', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<ReportView ticker="AAPL" ingesting={false} />)
    await waitFor(() =>
      expect(screen.getByText(REPORT.verdict)).toBeInTheDocument()
    )
  })

  it('hides header and trend in compact mode', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<ReportView ticker="AAPL" ingesting={false} compact />)
    await waitFor(() => expect(screen.getByText(REPORT.company_overview)).toBeInTheDocument())
    expect(screen.queryByText('10-K Fundamental Analysis')).not.toBeInTheDocument()
    expect(screen.queryByText(REPORT.trend_narrative)).not.toBeInTheDocument()
  })

  it('shows error in report data gracefully', async () => {
    axios.get.mockResolvedValue({ data: { ticker: 'AAPL', error: 'LLM timeout.' } })
    render(<ReportView ticker="AAPL" ingesting={false} />)
    await waitFor(() => expect(screen.getByText(/report error/i)).toBeInTheDocument())
    expect(screen.getByText(/LLM timeout/i)).toBeInTheDocument()
  })

  it('refresh button triggers refetch', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<ReportView ticker="AAPL" ingesting={false} />)
    await waitFor(() => expect(screen.getByText('Refresh')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Refresh'))
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2))
    expect(axios.get).toHaveBeenLastCalledWith(
      expect.stringContaining('refresh=true')
    )
  })

  it('calls onStatusChange done on success', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    const onStatusChange = vi.fn()
    render(<ReportView ticker="AAPL" ingesting={false} onStatusChange={onStatusChange} />)
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith('done'))
  })
})
