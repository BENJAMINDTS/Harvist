/**
 * Tests unitarios para DolibarrThirdparties.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrThirdparties: vi.fn(),
  searchDolibarrThirdparties: vi.fn(),
  createDolibarrThirdparty: vi.fn(),
  updateDolibarrThirdparty: vi.fn(),
  deleteDolibarrThirdparty: vi.fn(),
}))

import { listDolibarrThirdparties, searchDolibarrThirdparties } from '@/api/client'
import DolibarrThirdparties from '@/components/dolibarr/DolibarrThirdparties'

describe('DolibarrThirdparties', () => {
  beforeEach(() => {
    vi.mocked(listDolibarrThirdparties).mockResolvedValue({
      items: [{ id: 1, name: 'Proveedor Test', email: 'proveedor@test.com', client: 0, supplier: 1 }],
      total: 1,
      limit: 20,
      offset: 0,
    } as never)
    vi.mocked(searchDolibarrThirdparties).mockResolvedValue([] as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrThirdparties />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows thirdparties after loading', async () => {
    render(<DolibarrThirdparties />)
    await waitFor(() => {
      expect(screen.getByText('Proveedor Test')).toBeInTheDocument()
    })
  })
})
