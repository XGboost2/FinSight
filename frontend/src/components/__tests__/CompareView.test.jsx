import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import CompareView from '../CompareView'

const COMPARISON = {
  ticker1: 'AAPL',
  ticker2: 'MSFT',
  metrics1: { revenue_latest_year: '$394.3B', net_income_latest_year: '$96.9B', gross_margin_pct: '44.1%' },
  metrics2: { revenue_latest_year: '$211.9B', net_income_latest_year: '$72.4B', gross_margin_pct: '69.4%' },
  analysis: {
    financial_head_to_head: 'Apple has higher revenue, Microsoft has higher margins.',
    pros_cons: {
      AAPL: { pros: ['Strong brand', 'Ecosystem lock-in'], cons: ['Hardware dependency'] },
      MSFT: { pros: ['Cloud growth', 'Diversified revenue'], cons: ['Enterprise concentration'] },
    },
    strategic_positioning: 'Different strategies for different markets.',
    verdict: 'Both are strong long-term holds.',
  },
}

describe('CompareView', () => {
  it('shows loading state', () => {
    render(<CompareView comparison={null} loading error={null} onBack={vi.fn()} />)
    expect(screen.getByText(/generating analysis/i)).toBeInTheDocument()
  })

  it('shows error state with back button', () => {
    const onBack = vi.fn()
    render(<CompareView comparison={null} loading={false} error="Ingest failed." onBack={onBack} />)
    expect(screen.getByText('Ingest failed.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(onBack).toHaveBeenCalled()
  })

  it('renders nothing when no comparison and not loading', () => {
    const { container } = render(<CompareView comparison={null} loading={false} error={null} onBack={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows both tickers in the header', () => {
    render(<CompareView comparison={COMPARISON} loading={false} error={null} onBack={vi.fn()} />)
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
    expect(screen.getAllByText('MSFT').length).toBeGreaterThan(0)
  })

  it('renders financial metrics bar rows', () => {
    render(<CompareView comparison={COMPARISON} loading={false} error={null} onBack={vi.fn()} />)
    expect(screen.getByText('Revenue')).toBeInTheDocument()
    expect(screen.getByText('Net Income')).toBeInTheDocument()
    expect(screen.getByText('Gross Margin')).toBeInTheDocument()
    expect(screen.getByText('$394.3B')).toBeInTheDocument()
    expect(screen.getByText('$211.9B')).toBeInTheDocument()
  })

  it('shows financial head-to-head analysis', () => {
    render(<CompareView comparison={COMPARISON} loading={false} error={null} onBack={vi.fn()} />)
    expect(screen.getByText(COMPARISON.analysis.financial_head_to_head)).toBeInTheDocument()
  })

  it('shows pros and cons for both tickers', () => {
    render(<CompareView comparison={COMPARISON} loading={false} error={null} onBack={vi.fn()} />)
    expect(screen.getByText(/strong brand/i)).toBeInTheDocument()
    expect(screen.getByText(/cloud growth/i)).toBeInTheDocument()
    expect(screen.getByText(/hardware dependency/i)).toBeInTheDocument()
  })

  it('shows verdict section', () => {
    render(<CompareView comparison={COMPARISON} loading={false} error={null} onBack={vi.fn()} />)
    expect(screen.getByText(COMPARISON.analysis.verdict)).toBeInTheDocument()
  })

  it('calls onBack when back button clicked', () => {
    const onBack = vi.fn()
    render(<CompareView comparison={COMPARISON} loading={false} error={null} onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(onBack).toHaveBeenCalled()
  })
})
