import { render, screen, waitFor, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import axios from 'axios'
import StatusDots from '../StatusDots'

vi.mock('axios')

beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks() })
afterEach(() => { vi.useRealTimers() })

describe('StatusDots', () => {
  it('renders Redis and Qdrant labels', () => {
    axios.get.mockResolvedValue({ data: { redis_ok: true, qdrant_ok: true } })
    render(<StatusDots />)
    expect(screen.getByText('Redis')).toBeInTheDocument()
    expect(screen.getByText('Qdrant')).toBeInTheDocument()
  })

  it('shows green dots when both services are up', async () => {
    axios.get.mockResolvedValue({ data: { redis_ok: true, qdrant_ok: true } })
    render(<StatusDots />)
    await act(async () => { await Promise.resolve() })
    const dots = document.querySelectorAll('.status-ok')
    expect(dots).toHaveLength(2)
  })

  it('shows red dots when both services are down', async () => {
    axios.get.mockResolvedValue({ data: { redis_ok: false, qdrant_ok: false } })
    render(<StatusDots />)
    await act(async () => { await Promise.resolve() })
    const dots = document.querySelectorAll('.status-err')
    expect(dots).toHaveLength(2)
  })

  it('shows mixed state — redis up, qdrant down', async () => {
    axios.get.mockResolvedValue({ data: { redis_ok: true, qdrant_ok: false } })
    render(<StatusDots />)
    await act(async () => { await Promise.resolve() })
    expect(document.querySelectorAll('.status-ok')).toHaveLength(1)
    expect(document.querySelectorAll('.status-err')).toHaveLength(1)
  })

  it('shows red dots when health request fails', async () => {
    axios.get.mockRejectedValue(new Error('network error'))
    render(<StatusDots />)
    await act(async () => { await Promise.resolve() })
    const dots = document.querySelectorAll('.status-err')
    expect(dots).toHaveLength(2)
  })

  it('re-polls after 30 seconds', async () => {
    axios.get.mockResolvedValue({ data: { redis_ok: true, qdrant_ok: true } })
    render(<StatusDots />)
    await act(async () => { await Promise.resolve() })
    expect(axios.get).toHaveBeenCalledTimes(1)
    await act(async () => { vi.advanceTimersByTime(30_000); await Promise.resolve() })
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('shows grey dots before first response', () => {
    axios.get.mockImplementation(() => new Promise(() => {})) // never resolves
    render(<StatusDots />)
    const dots = document.querySelectorAll('.status-checking')
    expect(dots).toHaveLength(2)
  })
})
