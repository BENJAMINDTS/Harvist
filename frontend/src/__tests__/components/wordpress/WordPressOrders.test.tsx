/**
 * Tests unitarios para WordPressOrders.
 * listWordPressOrders returns WooOrder[] directly.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listWordPressOrders: vi.fn(),
  updateWordPressOrderStatus: vi.fn(),
}))

import { listWordPressOrders } from '@/api/client'
import WordPressOrders from '@/components/wordpress/WordPressOrders'

describe('WordPressOrders', () => {
  beforeEach(() => {
    vi.mocked(listWordPressOrders).mockResolvedValue([
      {
        id: 1001,
        number: '1001',
        status: 'processing',
        total: '49.90',
        billing: { first_name: 'Juan', last_name: 'García', email: 'juan@test.com' },
        date_created: '2024-01-01T00:00:00',
      },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<WordPressOrders />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows order data after loading', async () => {
    render(<WordPressOrders />)
    await waitFor(() => {
      // Order number may appear in multiple elements (header + row)
      const matches = screen.queryAllByText(/1001/)
      expect(matches.length).toBeGreaterThan(0)
    })
  })
})
