/**
 * Tests unitarios para ErrorBoundary.
 *
 * Verifica:
 * - Renderiza children cuando no hay error
 * - Captura error y muestra mensaje de error
 * - Muestra nombre del módulo en el mensaje de error
 * - Botón "Reintentar" limpia el error y vuelve a renderizar children
 *
 * @author BenjaminDTS
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { ErrorBoundary } from '@/components/ErrorBoundary'

const ThrowError = ({ message }: { message: string }) => {
  throw new Error(message)
}

const NormalChild = () => <div>contenido normal</div>

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <NormalChild />
      </ErrorBoundary>,
    )
    expect(screen.getByText('contenido normal')).toBeInTheDocument()
  })

  it('shows error message when child throws', () => {
    const consoleError = console.error
    console.error = () => {}

    render(
      <ErrorBoundary>
        <ThrowError message="algo salió mal" />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/algo salió mal/i)).toBeInTheDocument()
    console.error = consoleError
  })

  it('shows module name in error message when module prop provided', () => {
    const consoleError = console.error
    console.error = () => {}

    render(
      <ErrorBoundary module="Dolibarr">
        <ThrowError message="error de modulo" />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/Error en Dolibarr/i)).toBeInTheDocument()
    console.error = consoleError
  })

  it('resets error on retry button click', async () => {
    const consoleError = console.error
    console.error = () => {}

    const user = userEvent.setup()

    let shouldThrow = true
    const MaybeThrow = () => {
      if (shouldThrow) throw new Error('error temporal')
      return <div>recuperado</div>
    }

    render(
      <ErrorBoundary>
        <MaybeThrow />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/error temporal/i)).toBeInTheDocument()

    shouldThrow = false
    await user.click(screen.getByRole('button', { name: /reintentar/i }))

    expect(screen.getByText('recuperado')).toBeInTheDocument()
    console.error = consoleError
  })

  it('shows generic message when non-Error is thrown', () => {
    const consoleError = console.error
    console.error = () => {}

    const ThrowString = () => { throw 'string error' }

    render(
      <ErrorBoundary>
        <ThrowString />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/string error/i)).toBeInTheDocument()
    console.error = consoleError
  })
})
