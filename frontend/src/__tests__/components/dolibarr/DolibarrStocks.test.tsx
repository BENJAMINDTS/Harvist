/**
 * Tests unitarios para DolibarrStocks.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrWarehouses: vi.fn(),
  listDolibarrProducts: vi.fn(),
  getDolibarrProductStock: vi.fn(),
}))

import { listDolibarrWarehouses, listDolibarrProducts, getDolibarrProductStock } from '@/api/client'
import DolibarrStocks from '@/components/dolibarr/DolibarrStocks'

describe('DolibarrStocks', () => {
  beforeEach(() => {
    vi.mocked(listDolibarrWarehouses).mockResolvedValue({
      items: [{ id: 1, ref: 'ALM-001', label: 'Almacén Principal', description: '' }],
      total: 1,
      limit: 50,
      offset: 0,
      has_more: false,
    } as never)
    vi.mocked(listDolibarrProducts).mockResolvedValue({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
      has_more: false,
    } as never)
    vi.mocked(getDolibarrProductStock).mockResolvedValue({ items: [], total: 0 } as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrStocks />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows warehouses after loading', async () => {
    render(<DolibarrStocks />)
    await waitFor(() => {
      expect(screen.getAllByText(/Almacén Principal/i).length).toBeGreaterThan(0)
    })
  })
})
