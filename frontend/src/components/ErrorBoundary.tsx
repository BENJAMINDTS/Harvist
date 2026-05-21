/**
 * Componente ErrorBoundary genérico.
 * Captura errores de render en el subárbol y los muestra en pantalla
 * en lugar de dejar la página en blanco.
 *
 * @author Carlos Vico
 */
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Nombre del módulo que envuelve, para incluirlo en el mensaje de error. */
  module?: string
}

interface State {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: unknown): State {
    const message =
      error instanceof Error
        ? error.message
        : typeof error === 'string'
          ? error
          : 'Error inesperado en el renderizado.'
    return { hasError: true, message }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, message: '' })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 flex flex-col items-center justify-center gap-4 text-center">
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-lg w-full">
            <p className="text-sm font-semibold text-red-700 mb-1">
              {this.props.module ? `Error en ${this.props.module}` : 'Error de renderizado'}
            </p>
            <p className="text-xs text-red-600 font-mono break-all">{this.state.message}</p>
            <button
              onClick={this.handleReset}
              className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm rounded-lg font-medium"
            >
              Reintentar
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
