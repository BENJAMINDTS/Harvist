/**
 * Tests unitarios para Breadcrumb.
 *
 * Verifica:
 * - Renderiza botón "Dashboard"
 * - No muestra sub-sección cuando no se pasa subSection
 * - Muestra módulo actual en la ruta
 * - Muestra sub-sección cuando se pasa subSection
 * - Llama onBackToDashboard al hacer click en "Dashboard"
 * - No muestra separador de módulo cuando currentModule es "dashboard"
 *
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Breadcrumb } from '@/components/navigation/Breadcrumb'

describe('Breadcrumb', () => {
  it('renders Dashboard button', () => {
    render(
      <Breadcrumb
        currentModule="harvist"
        onBackToDashboard={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /dashboard/i })).toBeInTheDocument()
  })

  it('shows current module label in breadcrumb', () => {
    render(
      <Breadcrumb
        currentModule="dolibarr"
        currentLabel="Dolibarr"
        onBackToDashboard={vi.fn()}
      />,
    )
    expect(screen.getByText('Dolibarr')).toBeInTheDocument()
  })

  it('shows subSection when provided', () => {
    render(
      <Breadcrumb
        currentModule="odoo"
        subSection="Productos"
        onBackToDashboard={vi.fn()}
      />,
    )
    expect(screen.getByText('Productos')).toBeInTheDocument()
  })

  it('does not show subSection when not provided', () => {
    render(
      <Breadcrumb
        currentModule="odoo"
        onBackToDashboard={vi.fn()}
      />,
    )
    // Only Dashboard button and module label, no extra section
    expect(screen.queryByText('Productos')).not.toBeInTheDocument()
  })

  it('calls onBackToDashboard when Dashboard clicked', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()

    render(
      <Breadcrumb
        currentModule="wordpress"
        onBackToDashboard={onBack}
      />,
    )
    await user.click(screen.getByRole('button', { name: /dashboard/i }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('does not show chevron when currentModule is dashboard', () => {
    const { container } = render(
      <Breadcrumb
        currentModule="dashboard"
        onBackToDashboard={vi.fn()}
      />,
    )
    // No SVG chevrons besides the Dashboard button
    const svgs = container.querySelectorAll('svg')
    expect(svgs).toHaveLength(0)
  })
})
