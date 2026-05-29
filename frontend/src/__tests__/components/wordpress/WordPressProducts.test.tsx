/**
 * Tests unitarios para WordPressProducts.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listWordPressProducts: vi.fn(),
  createWordPressProduct: vi.fn(),
  updateWordPressProduct: vi.fn(),
  deleteWordPressProduct: vi.fn(),
  deleteWordPressProducts: vi.fn(),
  syncWordPressFromJob: vi.fn(),
  syncWordPressAllToDolibarr: vi.fn(),
  listWordPressCategories: vi.fn(),
  listWordPressBrands: vi.fn(),
  getWordPressCsvFields: vi.fn(),
  previewWordPressCsv: vi.fn(),
  importWordPressCsv: vi.fn(),
  getWordPressImportStatus: vi.fn(),
}))

import {
  listWordPressProducts,
  listWordPressCategories,
  listWordPressBrands,
  getWordPressCsvFields,
} from '@/api/client'
import WordPressProducts from '@/components/wordpress/WordPressProducts'

describe('WordPressProducts', () => {
  beforeEach(() => {
    vi.mocked(listWordPressProducts).mockResolvedValue({
      items: [{ id: 1, name: 'Camiseta', sku: 'CAM-001', regular_price: '19.99', status: 'publish' }],
      total: 1,
    } as never)
    vi.mocked(listWordPressCategories).mockResolvedValue([] as never)
    vi.mocked(listWordPressBrands).mockResolvedValue([] as never)
    vi.mocked(getWordPressCsvFields).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<WordPressProducts />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows products after loading', async () => {
    render(<WordPressProducts />)
    await waitFor(() => {
      expect(screen.getByText('Camiseta')).toBeInTheDocument()
    })
  })
})
