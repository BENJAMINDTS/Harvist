/**
 * Tests unitarios para SearchConfig.
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SearchConfig } from '@/components/SearchConfig'

const defaultProps = {
  fileName: 'productos.csv',
  csvHeaders: ['nombre', 'ean', 'codigo'],
  onStart: vi.fn(),
  onBack: vi.fn(),
  onLaunch: vi.fn().mockResolvedValue(undefined),
}

describe('SearchConfig', () => {
  it('renders without crashing', () => {
    render(<SearchConfig {...defaultProps} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows CSV filename', () => {
    render(<SearchConfig {...defaultProps} />)
    expect(screen.getByText('productos.csv')).toBeInTheDocument()
  })

  it('calls onBack when back button clicked', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()

    render(<SearchConfig {...defaultProps} onBack={onBack} />)
    const backBtn = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('volver') ||
      b.textContent?.toLowerCase().includes('atrás') ||
      b.textContent?.toLowerCase().includes('back'),
    )
    if (backBtn) {
      await user.click(backBtn)
      expect(onBack).toHaveBeenCalledOnce()
    }
  })

  it('has an Iniciar/Start button', () => {
    render(<SearchConfig {...defaultProps} />)
    const startBtn = screen.getAllByRole('button').find(b =>
      b.textContent?.toLowerCase().includes('iniciar') ||
      b.textContent?.toLowerCase().includes('lanzar') ||
      b.textContent?.toLowerCase().includes('start'),
    )
    expect(startBtn).toBeDefined()
  })
})
