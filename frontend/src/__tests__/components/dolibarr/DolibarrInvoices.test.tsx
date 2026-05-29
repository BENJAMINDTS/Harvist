/**
 * Tests unitarios para DolibarrInvoices.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrInvoices: vi.fn(),
}))

import { listDolibarrInvoices } from '@/api/client'
import DolibarrInvoices from '@/components/dolibarr/DolibarrInvoices'

describe('DolibarrInvoices', () => {
  beforeEach(() => {
    vi.mocked(listDolibarrInvoices).mockResolvedValue({
      items: [{ id: 1, ref: 'FAC-001', socid: 1, total_ttc: '119.90', statut: 1, date: '2024-01-01' }],
      total: 1,
      limit: 20,
      offset: 0,
    } as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrInvoices />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows invoices after loading', async () => {
    render(<DolibarrInvoices />)
    await waitFor(() => {
      expect(screen.getByText('FAC-001')).toBeInTheDocument()
    })
  })
})
