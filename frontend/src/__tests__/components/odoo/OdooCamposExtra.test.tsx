/**
 * Tests unitarios para OdooCamposExtra.
 * listOdooCategories returns { items: OdooCategory[] }.
 * @author BenjaminDTS
 */
import { render, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getOdooCategoryProperties: vi.fn(),
  addOdooCategoryProperty: vi.fn(),
  updateOdooCategoryProperty: vi.fn(),
  deleteOdooCategoryProperty: vi.fn(),
  listOdooCategories: vi.fn(),
  getOooCategoryTree: vi.fn(),
}))

import { getOdooCategoryProperties, listOdooCategories, getOooCategoryTree } from '@/api/client'
import OdooCamposExtra from '@/components/odoo/OdooCamposExtra'

describe('OdooCamposExtra', () => {
  beforeEach(() => {
    vi.mocked(listOdooCategories).mockResolvedValue({
      items: [{ id: 1, name: 'Electrónica', complete_name: 'Electrónica' }],
      total: 1,
      limit: 500,
      offset: 0,
    } as never)
    vi.mocked(getOooCategoryTree).mockResolvedValue([] as never)
    vi.mocked(getOdooCategoryProperties).mockResolvedValue([
      { name: 'aabb1122', string: 'Color', type: 'char' },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<OdooCamposExtra />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows category selector with categories', async () => {
    render(<OdooCamposExtra />)
    await waitFor(() => {
      const body = document.body.textContent ?? ''
      expect(body.includes('Electrónica')).toBe(true)
    })
  })
})
