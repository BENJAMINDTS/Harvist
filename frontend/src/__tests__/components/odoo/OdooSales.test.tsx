/**
 * Tests unitarios para OdooSales.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOdooSales: vi.fn(),
  confirmOdooSale: vi.fn(),
  cancelOdooSale: vi.fn(),
}))

import { listOdooSales } from '@/api/client'
import OdooSales from '@/components/odoo/OdooSales'

describe('OdooSales', () => {
  beforeEach(() => {
    vi.mocked(listOdooSales).mockResolvedValue({
      items: [{ id: 1, name: 'SO/001', partner_id: [1, 'Cliente'], state: 'sale', amount_total: 250 }],
      total: 1,
    } as never)
  })

  it('renders without crashing', () => {
    render(<OdooSales />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows sales after loading', async () => {
    render(<OdooSales />)
    await waitFor(() => {
      expect(screen.getByText('SO/001')).toBeInTheDocument()
    })
  })
})
