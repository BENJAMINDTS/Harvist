/**
 * Tests unitarios para OdooBrands.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOdooBrands: vi.fn(),
  createOdooBrand: vi.fn(),
  deleteOdooBrand: vi.fn(),
}))

import { listOdooBrands } from '@/api/client'
import OdooBrands from '@/components/odoo/OdooBrands'

describe('OdooBrands', () => {
  beforeEach(() => {
    vi.mocked(listOdooBrands).mockResolvedValue({
      items: [{ id: 1, name: 'Sony', complete_name: 'Marcas / Sony' }],
      total: 1,
    } as never)
  })

  it('renders without crashing', () => {
    render(<OdooBrands />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows brands after loading', async () => {
    render(<OdooBrands />)
    await waitFor(() => {
      expect(screen.getByText('Sony')).toBeInTheDocument()
    })
  })
})
