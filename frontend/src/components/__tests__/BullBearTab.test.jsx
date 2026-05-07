import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import axios from 'axios'
import BullBearTab from '../tabs/BullBearTab'

vi.mock('axios')

const REPORT = {
  ticker: 'AAPL',
  company_name: 'Apple Inc.',
  bull_case: [
    'Services segment growing at 15% YoY with high margins.',
    'iPhone installed base of 1.3B provides recurring upgrade revenue.',
  ],
  bear_case: [
    'Revenue declined 2.8% YoY driven by hardware softness.',
    'Increasing regulatory scrutiny in EU and US.',
  ],
  debate_transcript: [
    { role: 'Bull', argument: 'Services growth offsets hardware weakness.' },
    { role: 'Bear', argument: 'Hardware still 55% of revenue — cannot ignore decline.' },
    { role: 'Bull', argument: 'Margin expansion shows business quality.' },
    { role: 'Bear', argument: 'Regulatory fines remain an unresolved tail risk.' },
  ],
}

describe('BullBearTab', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows loading state while fetching', () => {
    axios.get.mockReturnValue(new Promise(() => {}))
    render(<BullBearTab ticker="AAPL" />)
    expect(screen.getByText(/loading debate/i)).toBeInTheDocument()
  })

  it('shows error message on failed fetch', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Report unavailable.' } } })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('Report unavailable.')).toBeInTheDocument())
  })

  it('renders agent header', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText('Bull vs Bear')).toBeInTheDocument())
  })

  it('renders all bull case points', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText(REPORT.bull_case[0])).toBeInTheDocument()
    )
    expect(screen.getByText(REPORT.bull_case[1])).toBeInTheDocument()
  })

  it('renders all bear case points', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText(REPORT.bear_case[0])).toBeInTheDocument()
    )
    expect(screen.getByText(REPORT.bear_case[1])).toBeInTheDocument()
  })

  it('renders debate transcript turns', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText(REPORT.debate_transcript[0].argument)).toBeInTheDocument()
    )
    expect(screen.getByText(REPORT.debate_transcript[1].argument)).toBeInTheDocument()
  })

  it('does not render transcript section when empty', async () => {
    axios.get.mockResolvedValue({ data: { ...REPORT, debate_transcript: [] } })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() => expect(screen.getByText(REPORT.bull_case[0])).toBeInTheDocument())
    expect(screen.queryByText('Debate Transcript')).not.toBeInTheDocument()
  })

  it('shows placeholder when no report and not loading', async () => {
    axios.get.mockResolvedValue({ data: null })
    render(<BullBearTab ticker="AAPL" />)
    await waitFor(() =>
      expect(screen.getByText(/run analysis on the fundamentals tab/i)).toBeInTheDocument()
    )
  })

  it('fetches from /report endpoint', async () => {
    axios.get.mockResolvedValue({ data: REPORT })
    render(<BullBearTab ticker="TSLA" />)
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining('/api/companies/TSLA/report')
    ))
  })
})
