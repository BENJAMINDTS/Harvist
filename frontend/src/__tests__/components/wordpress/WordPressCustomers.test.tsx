/**
 * Tests unitarios para WordPressCustomers.
 * listWordPressCustomers returns WooCustomer[] directly (array).
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listWordPressCustomers: vi.fn(),
  deleteWordPressCustomer: vi.fn(),
}))

import { listWordPressCustomers } from '@/api/client'
import WordPressCustomers from '@/components/wordpress/WordPressCustomers'

describe('WordPressCustomers', () => {
  beforeEach(() => {
    vi.mocked(listWordPressCustomers).mockResolvedValue([
      { id: 1, first_name: 'Ana', last_name: 'López', email: 'ana@test.com', orders_count: 2 },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<WordPressCustomers />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows customers after loading', async () => {
    render(<WordPressCustomers />)
    await waitFor(() => {
      expect(screen.getByText('ana@test.com')).toBeInTheDocument()
    })
  })
})
