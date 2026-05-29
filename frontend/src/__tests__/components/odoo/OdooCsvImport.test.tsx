/**
 * Tests unitarios para OdooCsvImport.
 * @author BenjaminDTS
 */
import { render } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  previewWordPressCsv: vi.fn(),
  getWordPressCsvFields: vi.fn(),
  importWordPressCsv: vi.fn(),
  getWordPressImportStatus: vi.fn(),
  listOdooCategories: vi.fn(),
  getOooCategoryTree: vi.fn(),
  listOdooBrands: vi.fn(),
  listOdooPublicCategories: vi.fn(),
}))

import { getWordPressCsvFields, listOdooCategories, getOooCategoryTree, listOdooBrands, listOdooPublicCategories } from '@/api/client'
import OdooCsvImport from '@/components/odoo/OdooCsvImport'

describe('OdooCsvImport', () => {
  beforeEach(() => {
    vi.mocked(getWordPressCsvFields).mockResolvedValue([] as never)
    vi.mocked(listOdooCategories).mockResolvedValue([] as never)
    vi.mocked(getOooCategoryTree).mockResolvedValue([] as never)
    vi.mocked(listOdooBrands).mockResolvedValue([] as never)
    vi.mocked(listOdooPublicCategories).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<OdooCsvImport onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows file input for CSV upload', () => {
    render(<OdooCsvImport onClose={vi.fn()} onSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]')
    expect(fileInput).toBeInTheDocument()
  })
})
