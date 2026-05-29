/**
 * Tests unitarios para OdooConfig.
 * @author BenjaminDTS
 */
import { render, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  getOdooConfig: vi.fn(),
  saveOdooConfig: vi.fn(),
}))

import { getOdooConfig } from '@/api/client'
import OdooConfig from '@/components/odoo/OdooConfig'

describe('OdooConfig', () => {
  beforeEach(() => {
    vi.mocked(getOdooConfig).mockResolvedValue({
      odoo_url: 'https://odoo.test',
      odoo_db: 'mydb',
      odoo_user: 'admin@test.com',
    } as never)
  })

  it('renders without crashing', () => {
    render(<OdooConfig onSaved={vi.fn()} status={null} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows form fields for connection config', async () => {
    render(<OdooConfig onSaved={vi.fn()} status={null} />)
    await waitFor(() => {
      const inputs = document.querySelectorAll('input')
      expect(inputs.length).toBeGreaterThan(0)
    })
  })
})
