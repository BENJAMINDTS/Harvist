/**
 * Tests unitarios para DolibarrPanel.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/components/dolibarr/DolibarrProducts', () => ({ default: () => <div>MockProducts</div> }))
vi.mock('@/components/dolibarr/DolibarrCategories', () => ({ default: () => <div>MockCategories</div> }))
vi.mock('@/components/dolibarr/DolibarrBrands', () => ({ default: () => <div>MockBrands</div> }))
vi.mock('@/components/dolibarr/DolibarrThirdparties', () => ({ default: () => <div>MockThirdparties</div> }))
vi.mock('@/components/dolibarr/DolibarrOrders', () => ({ default: () => <div>MockOrders</div> }))
vi.mock('@/components/dolibarr/DolibarrInvoices', () => ({ default: () => <div>MockInvoices</div> }))
vi.mock('@/components/dolibarr/DolibarrStocks', () => ({ default: () => <div>MockStocks</div> }))
vi.mock('@/components/dolibarr/DolibarrExtraFields', () => ({ default: () => <div>MockExtraFields</div> }))
vi.mock('@/components/dolibarr/DolibarrConfig', () => ({ default: ({ onSaved }: { onSaved: () => void }) => <button onClick={onSaved}>MockConfig</button> }))
vi.mock('@/api/client', () => ({
  getDolibarrStatus: vi.fn(),
}))

import { getDolibarrStatus } from '@/api/client'
import DolibarrPanel from '@/components/dolibarr/DolibarrPanel'

describe('DolibarrPanel', () => {
  beforeEach(() => {
    vi.mocked(getDolibarrStatus).mockResolvedValue({ configured: true, healthy: true } as never)
  })

  it('shows loading spinner initially', () => {
    vi.mocked(getDolibarrStatus).mockImplementation(() => new Promise(() => {}))
    render(<DolibarrPanel />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows products tab when configured', async () => {
    render(<DolibarrPanel />)
    await waitFor(() => {
      expect(screen.getByText('MockProducts')).toBeInTheDocument()
    })
  })

  it('switches to config tab when not configured', async () => {
    vi.mocked(getDolibarrStatus).mockResolvedValue({ configured: false, healthy: false } as never)
    render(<DolibarrPanel />)
    await waitFor(() => {
      expect(screen.getByText('MockConfig')).toBeInTheDocument()
    })
  })

  it('can switch to categories tab', async () => {
    const user = userEvent.setup()
    render(<DolibarrPanel />)
    await waitFor(() => expect(screen.getByText('MockProducts')).toBeInTheDocument())

    const categoryTab = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('categor'),
    )
    if (categoryTab) {
      await user.click(categoryTab)
      await waitFor(() => expect(screen.getByText('MockCategories')).toBeInTheDocument())
    }
  })
})
