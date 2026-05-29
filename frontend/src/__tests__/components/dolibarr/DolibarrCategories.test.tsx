/**
 * Tests unitarios para DolibarrCategories.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getDolibarrCategoryTree: vi.fn(),
  listDolibarrCategories: vi.fn(),
  createDolibarrCategory: vi.fn(),
  updateDolibarrCategory: vi.fn(),
  deleteDolibarrCategory: vi.fn(),
  assignDolibarrProductToCategory: vi.fn(),
}))

import { getDolibarrCategoryTree } from '@/api/client'
import DolibarrCategories from '@/components/dolibarr/DolibarrCategories'

describe('DolibarrCategories', () => {
  beforeEach(() => {
    vi.mocked(getDolibarrCategoryTree).mockResolvedValue([
      { id: 1, label: 'Electrónica', type: 'product', children: [] },
      { id: 2, label: 'Ropa', type: 'product', children: [] },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrCategories />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows categories after loading', async () => {
    render(<DolibarrCategories />)
    await waitFor(() => {
      expect(screen.getByText('Electrónica')).toBeInTheDocument()
    })
  })
})
