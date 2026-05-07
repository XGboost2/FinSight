import { render, screen } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import Dashboard from '../Dashboard'

const COMPANY = { ticker: 'AAPL', name: 'Apple Inc.' }

const DASHBOARD = {
  executive_summary: 'Apple reported strong results.',
  revenue_latest_year: '$394.3B',
  revenue_yoy_change: '-2.8%',
  net_income_latest_year: '$96.9B',
  gross_margin_pct: '44.1%',
  top_3_risk_factors: ['Competition', 'Supply chain', 'Regulatory'],
  primary_revenue_segments: ['iPhone', 'Services', 'Mac'],
  management_outlook_summary: 'Management is optimistic.',
}

describe('Dashboard', () => {
  it('renders nothing when no company selected', () => {
    const { container } = render(<Dashboard company={null} dashboard={null} loading={false} error={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows ticker and company name', () => {
    render(<Dashboard company={COMPANY} dashboard={null} loading={false} error={null} />)
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
  })

  it('shows loading indicator while fetching', () => {
    render(<Dashboard company={COMPANY} dashboard={null} loading error={null} />)
    expect(screen.getByText(/fetching filings/i)).toBeInTheDocument()
  })

  it('shows error message', () => {
    render(<Dashboard company={COMPANY} dashboard={null} loading={false} error="Filing not found." />)
    expect(screen.getByText('Filing not found.')).toBeInTheDocument()
  })

  it('renders all metric cards when dashboard provided', () => {
    render(<Dashboard company={COMPANY} dashboard={DASHBOARD} loading={false} error={null} />)
    expect(screen.getByText('$394.3B')).toBeInTheDocument()
    expect(screen.getByText('$96.9B')).toBeInTheDocument()
    expect(screen.getByText('44.1%')).toBeInTheDocument()
    expect(screen.getByText('-2.8%')).toBeInTheDocument()
  })

  it('renders risk factors list', () => {
    render(<Dashboard company={COMPANY} dashboard={DASHBOARD} loading={false} error={null} />)
    expect(screen.getByText('Competition')).toBeInTheDocument()
    expect(screen.getByText('Supply chain')).toBeInTheDocument()
    expect(screen.getByText('Regulatory')).toBeInTheDocument()
  })

  it('renders revenue segments', () => {
    render(<Dashboard company={COMPANY} dashboard={DASHBOARD} loading={false} error={null} />)
    expect(screen.getByText('iPhone')).toBeInTheDocument()
    expect(screen.getByText('Services')).toBeInTheDocument()
    expect(screen.getByText('Mac')).toBeInTheDocument()
  })

  it('renders executive summary', () => {
    render(<Dashboard company={COMPANY} dashboard={DASHBOARD} loading={false} error={null} />)
    expect(screen.getByText('Apple reported strong results.')).toBeInTheDocument()
  })

  it('renders management outlook', () => {
    render(<Dashboard company={COMPANY} dashboard={DASHBOARD} loading={false} error={null} />)
    expect(screen.getByText(/"Management is optimistic."/)).toBeInTheDocument()
  })

  it('does not render sections when dashboard is null', () => {
    render(<Dashboard company={COMPANY} dashboard={null} loading={false} error={null} />)
    expect(screen.queryByText('Revenue Segments')).not.toBeInTheDocument()
    expect(screen.queryByText('Top Risk Factors')).not.toBeInTheDocument()
  })
})
