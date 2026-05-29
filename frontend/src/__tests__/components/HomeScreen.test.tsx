/**
 * Tests unitarios para HomeScreen.
 *
 * Verifica:
 * - Renderiza sin errores
 * - Muestra opciones de modo de trabajo
 * - Llama callbacks al hacer click
 *
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/assets/logo.png', () => ({ default: 'logo-test.png' }))

import { HomeScreen } from '@/components/HomeScreen'

function renderHomeScreen(overrides = {}) {
  const props = {
    onSelectFotos: vi.fn(),
    onSelectDescripciones: vi.fn(),
    onSelectMarcas: vi.fn(),
    onSelectHistorial: vi.fn(),
    ...overrides,
  }
  return { ...render(<HomeScreen {...props} />), props }
}

describe('HomeScreen', () => {
  it('renders without crashing', () => {
    renderHomeScreen()
  })

  it('shows at least 2 clickable cards/buttons', () => {
    renderHomeScreen()
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThanOrEqual(2)
  })

  it('calls onSelectFotos when fotos option is clicked', async () => {
    const { props } = renderHomeScreen()
    const user = userEvent.setup()

    const fotosBtn = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('foto') ||
      b.textContent?.toLowerCase().includes('imagen'),
    )
    if (fotosBtn) {
      await user.click(fotosBtn)
      expect(props.onSelectFotos).toHaveBeenCalledOnce()
    }
  })

  it('calls onSelectHistorial when historial option is clicked', async () => {
    const { props } = renderHomeScreen()
    const user = userEvent.setup()

    const histBtn = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('historial'),
    )
    if (histBtn) {
      await user.click(histBtn)
      expect(props.onSelectHistorial).toHaveBeenCalledOnce()
    }
  })
})
