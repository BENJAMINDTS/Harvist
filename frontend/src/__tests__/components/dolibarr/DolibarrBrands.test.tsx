/**
 * Tests unitarios para DolibarrBrands.
 * listDolibarrBrands returns { items: DolibarrCategory[]; total; limit; offset; has_more }.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrBrands: vi.fn(),
  createDolibarrBrand: vi.fn(),
  updateDolibarrCategory: vi.fn(),
  deleteDolibarrCategory: vi.fn(),
}))

import { listDolibarrBrands } from '@/api/client'
import DolibarrBrands from '@/components/dolibarr/DolibarrBrands'

describe('DolibarrBrands', () => {
  beforeEach(() => {
    vi.mocked(listDolibarrBrands).mockResolvedValue({
      items: [
        { id: 1, label: 'Nike', description: '' },
        { id: 2, label: 'Adidas', description: '' },
      ],
      total: 2,
      limit: 200,
      offset: 0,
      has_more: false,
    } as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrBrands />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows brands after loading', async () => {
    render(<DolibarrBrands />)
    await waitFor(() => {
      expect(screen.getByText('Nike')).toBeInTheDocument()
    })
  })
})
