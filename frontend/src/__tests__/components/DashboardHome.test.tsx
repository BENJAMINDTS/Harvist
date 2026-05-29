/**
 * Tests unitarios para DashboardHome.
 *
 * Verifica:
 * - Renderiza los 4 módulos (Harvist, Dolibarr, Odoo, WordPress)
 * - Llama onSelectHarvist al hacer click en la card de Harvist
 * - Llama onSelectDolibarr al hacer click en la card de Dolibarr
 * - Llama onSelectOdoo al hacer click en la card de Odoo
 * - Llama onSelectWordpress al hacer click en la card de WordPress
 *
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/assets/logo.png', () => ({ default: 'logo-test.png' }))

import { DashboardHome } from '@/components/DashboardHome'

function renderDashboard(overrides = {}) {
  const props = {
    onSelectHarvist: vi.fn(),
    onSelectDolibarr: vi.fn(),
    onSelectOdoo: vi.fn(),
    onSelectWordpress: vi.fn(),
    ...overrides,
  }
  return { ...render(<DashboardHome {...props} />), props }
}

describe('DashboardHome', () => {
  it('renders all 4 module cards', () => {
    renderDashboard()
    // Use getAllByText to handle multiple matches; just verify at least one each
    expect(screen.getAllByText(/harvist/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/dolibarr/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/odoo/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/wordpress/i).length).toBeGreaterThan(0)
  })

  it('calls onSelectHarvist when Harvist card is clicked', async () => {
    const { props } = renderDashboard()
    const user = userEvent.setup()

    const card = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('harvist'),
    )
    expect(card).toBeDefined()
    await user.click(card!)
    expect(props.onSelectHarvist).toHaveBeenCalledOnce()
  })

  it('calls onSelectDolibarr when Dolibarr card is clicked', async () => {
    const { props } = renderDashboard()
    const user = userEvent.setup()

    const card = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('dolibarr'),
    )
    await user.click(card!)
    expect(props.onSelectDolibarr).toHaveBeenCalledOnce()
  })

  it('calls onSelectOdoo when Odoo card is clicked', async () => {
    const { props } = renderDashboard()
    const user = userEvent.setup()

    const card = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('odoo'),
    )
    await user.click(card!)
    expect(props.onSelectOdoo).toHaveBeenCalledOnce()
  })

  it('calls onSelectWordpress when WordPress card is clicked', async () => {
    const { props } = renderDashboard()
    const user = userEvent.setup()

    const card = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('wordpress'),
    )
    await user.click(card!)
    expect(props.onSelectWordpress).toHaveBeenCalledOnce()
  })
})
