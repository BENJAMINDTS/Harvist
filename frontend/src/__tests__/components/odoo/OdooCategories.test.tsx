/**
 * Tests unitarios para OdooCategories.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getOooCategoryTree: vi.fn(),
  listOdooCategories: vi.fn(),
  createOdooCategory: vi.fn(),
  updateOdooCategory: vi.fn(),
  deleteOdooCategory: vi.fn(),
}))

import { getOooCategoryTree, listOdooCategories } from '@/api/client'
import OdooCategories from '@/components/odoo/OdooCategories'

describe('OdooCategories', () => {
  beforeEach(() => {
    vi.mocked(getOooCategoryTree).mockResolvedValue([
      { id: 1, name: 'Electrónica', complete_name: 'Electrónica', children: [] },
    ] as never)
    vi.mocked(listOdooCategories).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<OdooCategories />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows categories after loading', async () => {
    render(<OdooCategories />)
    await waitFor(() => {
      expect(screen.getByText('Electrónica')).toBeInTheDocument()
    })
  })
})
