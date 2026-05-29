/**
 * Tests unitarios para OdooProductProperties.
 * @author BenjaminDTS
 */
import { render } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getOdooProductProperties: vi.fn(),
  setOdooProductProperties: vi.fn(),
  deleteOdooProductProperty: vi.fn(),
  listOdooProducts: vi.fn(),
}))

import { getOdooProductProperties, listOdooProducts } from '@/api/client'
import OdooProductProperties from '@/components/odoo/OdooProductProperties'

describe('OdooProductProperties', () => {
  beforeEach(() => {
    vi.mocked(getOdooProductProperties).mockResolvedValue([] as never)
    vi.mocked(listOdooProducts).mockResolvedValue({ items: [], total: 0 } as never)
  })

  it('renders without crashing', () => {
    render(<OdooProductProperties productId={null} categoryId={false} />)
    expect(document.body).toBeInTheDocument()
  })
})
