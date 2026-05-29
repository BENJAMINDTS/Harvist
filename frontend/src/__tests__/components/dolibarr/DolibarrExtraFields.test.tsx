/**
 * Tests unitarios para DolibarrExtraFields.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  listDolibarrExtraFields: vi.fn(),
  createDolibarrExtraField: vi.fn(),
  deleteDolibarrExtraField: vi.fn(),
}))

import { listDolibarrExtraFields } from '@/api/client'
import DolibarrExtraFields from '@/components/dolibarr/DolibarrExtraFields'

describe('DolibarrExtraFields', () => {
  beforeEach(() => {
    vi.mocked(listDolibarrExtraFields).mockResolvedValue([
      { attrname: 'color', label: 'Color', type: 'varchar', elementtype: 'product', size: 50, required: 0 },
    ] as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrExtraFields />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows extra fields after loading', async () => {
    render(<DolibarrExtraFields />)
    await waitFor(() => {
      expect(screen.getByText('Color')).toBeInTheDocument()
    })
  })
})
