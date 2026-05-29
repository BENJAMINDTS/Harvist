/**
 * Tests unitarios para OooPurchases.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOooPurchases: vi.fn(),
  confirmOooPurchase: vi.fn(),
  cancelOooPurchase: vi.fn(),
}))

import { listOooPurchases } from '@/api/client'
import OooPurchases from '@/components/odoo/OdooPurchases'

describe('OooPurchases', () => {
  beforeEach(() => {
    vi.mocked(listOooPurchases).mockResolvedValue({
      items: [{ id: 1, name: 'PO/001', partner_id: [1, 'Proveedor'], state: 'draft', amount_total: 500 }],
      total: 1,
    } as never)
  })

  it('renders without crashing', () => {
    render(<OooPurchases />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows purchases after loading', async () => {
    render(<OooPurchases />)
    await waitFor(() => {
      expect(screen.getByText('PO/001')).toBeInTheDocument()
    })
  })
})
