import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import axios from 'axios'
import RiskTab from '../tabs/RiskTab'

vi.mock('axios')

const REPORT = {
  ticker: 'AAPL',
  risk_score: 0.34,
  risk_factors: ['Regulatory risk in EU', 'Supply chain concentration', 'FX headwinds'],
}

const DIFF = {
  ticker: 'AAPL',
  current_year: '2025',
  prior_year: '2024',
  item_1a: {
    section: 'Risk Factors (Item 1A)',
    current_year: '2025',
    prior_year: '2024',
    summary: 'AI regulation added as a new risk this year.',
    new: ['AI regulatory compliance requirements'],
    changed: [],
    removed: [],
    unchanged_count: 18,
  },
}

const EVENTS = {
  events: [
    { date: '2026-01-15', event_type: 'earnings', summary: 'Q1 FY2026 earnings released.' },
    { date: '2025-10-03', event_type: 'legal', summary: 'DOJ investigation disclosed.' },
  ],
}

describe('RiskTab', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows loading state while fetching', () => {
    axios.get.mockReturnValue(new Promise(() => {}))
    render(<RiskTab ticker="AAPL" />)
    expect(screen.getByText(/loading risk analysis/i)).toBeInTheDocument()
  })

  it('shows error message on failure', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Risk data unavailable.' } } })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('Risk data unavailable.')).toBeInTheDocument())
  })

  it('renders agent header', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('Risk Analyst')).toBeInTheDocument())
  })

  it('renders risk score gauge', async () => {
    axios.get
      .mockResolvedValueOnce({ data: REPORT })
      .mockResolvedValueOnce({ data: null })
      .mockResolvedValueOnce({ data: { events: [] } })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText(/low/i)).toBeInTheDocument())
  })

  it('renders top risk factors from report', async () => {
    axios.get
      .mockResolvedValueOnce({ data: REPORT })
      .mockResolvedValueOnce({ data: null })
      .mockResolvedValueOnce({ data: { events: [] } })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText('Regulatory risk in EU')).toBeInTheDocument()
    )
    expect(screen.getByText('Supply chain concentration')).toBeInTheDocument()
    expect(screen.getByText('FX headwinds')).toBeInTheDocument()
  })

  it('renders 8-K events when available', async () => {
    axios.get
      .mockResolvedValueOnce({ data: REPORT })
      .mockResolvedValueOnce({ data: null })
      .mockResolvedValueOnce({ data: EVENTS })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText('Q1 FY2026 earnings released.')).toBeInTheDocument()
    )
    expect(screen.getByText('DOJ investigation disclosed.')).toBeInTheDocument()
  })

  it('renders YoY diff section when diff available', async () => {
    axios.get
      .mockResolvedValueOnce({ data: REPORT })
      .mockResolvedValueOnce({ data: DIFF })
      .mockResolvedValueOnce({ data: { events: [] } })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText('AI regulation added as a new risk this year.')).toBeInTheDocument()
    )
    expect(screen.getByText('AI regulatory compliance requirements')).toBeInTheDocument()
  })

  it('renders unchanged paragraph count', async () => {
    axios.get
      .mockResolvedValueOnce({ data: REPORT })
      .mockResolvedValueOnce({ data: DIFF })
      .mockResolvedValueOnce({ data: { events: [] } })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText(/18 paragraphs unchanged/i)).toBeInTheDocument()
    )
  })

  it('shows placeholder when no report and not loading', async () => {
    axios.get.mockResolvedValue({ data: null })
    render(<RiskTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText(/run analysis on the fundamentals tab/i)).toBeInTheDocument()
    )
  })
})
