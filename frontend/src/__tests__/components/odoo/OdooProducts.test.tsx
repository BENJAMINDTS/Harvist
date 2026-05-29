/**
 * Tests unitarios para OdooProducts.
 * listOdooProducts returns PaginatedResponse<OdooProduct>.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOdooProducts: vi.fn(),
  createOdooProduct: vi.fn(),
  updateOdooProduct: vi.fn(),
  deleteOdooProduct: vi.fn(),
  deleteOdooProducts: vi.fn(),
  listOdooCategories: vi.fn(),
  getOooCategoryTree: vi.fn(),
  listOdooBrands: vi.fn(),
  getWordPressCsvFields: vi.fn(),
  previewWordPressCsv: vi.fn(),
  importWordPressCsv: vi.fn(),
  getWordPressImportStatus: vi.fn(),
  listOdooPublicCategories: vi.fn(),
  setOdooProductProperties: vi.fn(),
}))

import {
  listOdooProducts,
  listOdooCategories,
  listOdooBrands,
  getWordPressCsvFields,
  getOooCategoryTree,
  listOdooPublicCategories,
} from '@/api/client'
import OdooProducts from '@/components/odoo/OdooProducts'

describe('OdooProducts', () => {
  beforeEach(() => {
    vi.mocked(listOdooProducts).mockResolvedValue({
      items: [
        {
          id: 1,
          name: 'Laptop X',
          default_code: 'LAP-001',
          list_price: 999,
          active: true,
          qty_available: 5,
          type: 'consu',
          categ_id: [1, 'General'],
        },
      ],
      total: 1,
      limit: 10,
      offset: 0,
      has_more: false,
    } as never)
    vi.mocked(listOdooCategories).mockResolvedValue([] as never)
    vi.mocked(getOooCategoryTree).mockResolvedValue([] as never)
    vi.mocked(listOdooBrands).mockResolvedValue([] as never)
    vi.mocked(getWordPressCsvFields).mockResolvedValue([] as never)
    vi.mocked(listOdooPublicCategories).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<OdooProducts />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows products after loading', async () => {
    render(<OdooProducts />)
    await waitFor(() => {
      expect(screen.getByText('Laptop X')).toBeInTheDocument()
    })
  })
})
