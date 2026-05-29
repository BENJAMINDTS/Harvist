/**
 * Tests unitarios para OdooPartners.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOdooPartners: vi.fn(),
  updateOdooPartner: vi.fn(),
  deleteOdooPartner: vi.fn(),
}))

import { listOdooPartners } from '@/api/client'
import OdooPartners from '@/components/odoo/OdooPartners'

describe('OdooPartners', () => {
  beforeEach(() => {
    vi.mocked(listOdooPartners).mockResolvedValue({
      items: [{ id: 1, name: 'Acme Corp', email: 'acme@test.com', customer_rank: 1, supplier_rank: 0 }],
      total: 1,
    } as never)
  })

  it('renders without crashing', () => {
    render(<OdooPartners />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows partners after loading', async () => {
    render(<OdooPartners />)
    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })
  })
})
