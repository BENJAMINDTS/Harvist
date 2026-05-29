/**
 * Tests unitarios para OdooPanel.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/components/odoo/OdooProducts', () => ({ default: () => <div>MockOdooProducts</div> }))
vi.mock('@/components/odoo/OdooCategories', () => ({ default: () => <div>MockOdooCategories</div> }))
vi.mock('@/components/odoo/OdooBrands', () => ({ default: () => <div>MockOdooBrands</div> }))
vi.mock('@/components/odoo/OdooEcommerceCategories', () => ({ default: () => <div>MockEcomm</div> }))
vi.mock('@/components/odoo/OdooPartners', () => ({ default: () => <div>MockPartners</div> }))
vi.mock('@/components/odoo/OdooPurchases', () => ({ default: () => <div>MockPurchases</div> }))
vi.mock('@/components/odoo/OdooSales', () => ({ default: () => <div>MockSales</div> }))
vi.mock('@/components/odoo/OdooInvoices', () => ({ default: () => <div>MockOdooInvoices</div> }))
vi.mock('@/components/odoo/OdooInventory', () => ({ default: () => <div>MockInventory</div> }))
vi.mock('@/components/odoo/OdooCamposExtra', () => ({ default: () => <div>MockCamposExtra</div> }))
vi.mock('@/components/odoo/OdooConfig', () => ({ default: () => <div>MockOdooConfig</div> }))
vi.mock('@/api/client', () => ({
  getOdooStatus: vi.fn(),
}))

import { getOdooStatus } from '@/api/client'
import OdooPanel from '@/components/odoo/OdooPanel'

describe('OdooPanel', () => {
  beforeEach(() => {
    vi.mocked(getOdooStatus).mockResolvedValue({ configured: true, healthy: true } as never)
  })

  it('shows loading spinner initially', () => {
    vi.mocked(getOdooStatus).mockImplementation(() => new Promise(() => {}))
    render(<OdooPanel />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows products tab when configured', async () => {
    render(<OdooPanel />)
    await waitFor(() => {
      expect(screen.getByText('MockOdooProducts')).toBeInTheDocument()
    })
  })

  it('switches to config tab when not configured', async () => {
    vi.mocked(getOdooStatus).mockResolvedValue({ configured: false, healthy: false } as never)
    render(<OdooPanel />)
    await waitFor(() => {
      expect(screen.getByText('MockOdooConfig')).toBeInTheDocument()
    })
  })
})
