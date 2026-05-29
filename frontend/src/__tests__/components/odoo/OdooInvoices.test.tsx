/**
 * Tests unitarios para OdooInvoices.
 * formatAmount calls .toFixed() on amount_total — include it in mock.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listOdooInvoices: vi.fn(),
  validateOdooInvoice: vi.fn(),
  cancelOdooInvoice: vi.fn(),
}))

import { listOdooInvoices } from '@/api/client'
import OdooInvoices from '@/components/odoo/OdooInvoices'

describe('OdooInvoices', () => {
  beforeEach(() => {
    vi.mocked(listOdooInvoices).mockResolvedValue({
      items: [
        {
          id: 1,
          name: 'INV/001',
          partner_id: [1, 'Cliente'],
          state: 'posted',
          amount_total: 119.90,
          amount_residual: 0,
          currency_id: [1, 'EUR'],
          invoice_date: '2024-01-01',
          move_type: 'out_invoice',
          payment_state: 'paid',
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
      has_more: false,
    } as never)
  })

  it('renders without crashing', () => {
    render(<OdooInvoices />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows invoices after loading', async () => {
    render(<OdooInvoices />)
    await waitFor(() => {
      expect(screen.getByText('INV/001')).toBeInTheDocument()
    })
  })
})
