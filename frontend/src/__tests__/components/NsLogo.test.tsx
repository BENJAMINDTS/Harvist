/**
 * Tests unitarios para NsLogo.
 *
 * Verifica:
 * - Renderiza imagen con alt correcto
 * - Aplica tamaño por defecto (48px)
 * - Aplica tamaño personalizado cuando se pasa size prop
 *
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/assets/logo.png', () => ({ default: 'logo-test.png' }))

import { NsLogo } from '@/components/NsLogo'

describe('NsLogo', () => {
  it('renders image with alt text', () => {
    render(<NsLogo />)
    const img = screen.getByRole('img', { name: /logotipo/i })
    expect(img).toBeInTheDocument()
  })

  it('uses default size of 48', () => {
    render(<NsLogo />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('width', '48')
    expect(img).toHaveAttribute('height', '48')
  })

  it('applies custom size when provided', () => {
    render(<NsLogo size={96} />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('width', '96')
    expect(img).toHaveAttribute('height', '96')
  })
})
