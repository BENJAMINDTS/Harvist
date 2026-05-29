/**
 * Tests unitarios para OdooInventory.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOdooStock: vi.fn(),
  listOdooLocations: vi.fn(),
  adjustOdooStock: vi.fn(),
  updateOdooStockQuant: vi.fn(),
  deleteOdooStockQuant: vi.fn(),
}))

import { listOdooStock, listOdooLocations } from '@/api/client'
import OdooInventory from '@/components/odoo/OdooInventory'

describe('OdooInventory', () => {
  beforeEach(() => {
    vi.mocked(listOdooStock).mockResolvedValue({
      items: [{ id: 1, product_id: [1, 'Laptop'], quantity: 5, reserved_quantity: 0, location_id: [1, 'WH/Stock'] }],
      total: 1,
    } as never)
    vi.mocked(listOdooLocations).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<OdooInventory />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows stock items after loading', async () => {
    render(<OdooInventory />)
    await waitFor(() => {
      expect(screen.getByText('Laptop')).toBeInTheDocument()
    })
  })
})
