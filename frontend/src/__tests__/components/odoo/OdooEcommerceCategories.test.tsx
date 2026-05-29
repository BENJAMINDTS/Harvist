/**
 * Tests unitarios para OdooEcommerceCategories.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getOdooPublicCategoryTree: vi.fn(),
  listOdooPublicCategories: vi.fn(),
  createOdooPublicCategory: vi.fn(),
  updateOdooPublicCategory: vi.fn(),
  deleteOdooPublicCategory: vi.fn(),
}))

import { getOdooPublicCategoryTree, listOdooPublicCategories } from '@/api/client'
import OdooEcommerceCategories from '@/components/odoo/OdooEcommerceCategories'

describe('OdooEcommerceCategories', () => {
  beforeEach(() => {
    vi.mocked(getOdooPublicCategoryTree).mockResolvedValue([
      { id: 1, name: 'Tienda Web', children: [] },
    ] as never)
    vi.mocked(listOdooPublicCategories).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<OdooEcommerceCategories />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows categories after loading', async () => {
    render(<OdooEcommerceCategories />)
    await waitFor(() => {
      expect(screen.getByText('Tienda Web')).toBeInTheDocument()
    })
  })
})
