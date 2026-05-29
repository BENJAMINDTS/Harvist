/**
 * Tests unitarios para DolibarrProducts.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrProducts: vi.fn(),
  getDolibarrProductFields: vi.fn(),
  deleteDolibarrProduct: vi.fn(),
  syncDolibarrFromJob: vi.fn(),
  createDolibarrProduct: vi.fn(),
  updateDolibarrProduct: vi.fn(),
  previewDolibarrCsv: vi.fn(),
  importDolibarrCsv: vi.fn(),
  getDolibarrImportStatus: vi.fn(),
  deleteDolibarrProducts: vi.fn(),
  listDolibarrCategories: vi.fn(),
  listDolibarrBrands: vi.fn(),
  syncDolibarrAllToWordPress: vi.fn(),
}))

import {
  listDolibarrProducts,
  getDolibarrProductFields,
  listDolibarrCategories,
  listDolibarrBrands,
} from '@/api/client'
import DolibarrProducts from '@/components/dolibarr/DolibarrProducts'

describe('DolibarrProducts', () => {
  beforeEach(() => {
    vi.mocked(getDolibarrProductFields).mockResolvedValue([
      { name: 'ref', label: 'Referencia', type: 'varchar' as never, required: true },
    ] as never)
    vi.mocked(listDolibarrProducts).mockResolvedValue({
      items: [{ id: 1, ref: 'PROD-001', label: 'Producto Test', price: '9.99' }],
      total: 1,
      limit: 10,
      offset: 0,
      has_more: false,
    } as never)
    vi.mocked(listDolibarrCategories).mockResolvedValue({ data: { items: [] } } as never)
    vi.mocked(listDolibarrBrands).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrProducts />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows products after loading', async () => {
    render(<DolibarrProducts />)
    await waitFor(() => {
      expect(screen.getByText('PROD-001')).toBeInTheDocument()
    })
  })

  it('shows empty state when no products', async () => {
    vi.mocked(listDolibarrProducts).mockResolvedValueOnce({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
      has_more: false,
    } as never)
    render(<DolibarrProducts />)
    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).not.toBeInTheDocument()
    })
  })
})
