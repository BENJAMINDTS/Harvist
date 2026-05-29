/**
 * Tests unitarios para DolibarrOrders.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrOrders: vi.fn(),
}))

import { listDolibarrOrders } from '@/api/client'
import DolibarrOrders from '@/components/dolibarr/DolibarrOrders'

describe('DolibarrOrders', () => {
  beforeEach(() => {
    vi.mocked(listDolibarrOrders).mockResolvedValue({
      items: [{ id: 1, ref: 'SO-001', socid: 1, total_ttc: '99.90', statut: 1, date: '2024-01-01' }],
      total: 1,
      limit: 20,
      offset: 0,
    } as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrOrders />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows orders after loading', async () => {
    render(<DolibarrOrders />)
    await waitFor(() => {
      expect(screen.getByText('SO-001')).toBeInTheDocument()
    })
  })
})
