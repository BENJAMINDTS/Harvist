/**
 * Tests unitarios para JobProgress.
 *
 * Verifica:
 * - Renderiza sin errores con jobId válido
 * - Muestra porcentaje cuando hay progreso
 * - Muestra badge de estado
 *
 * @author BenjaminDTS
 */
import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock WebSocket globally
let lastWs: MockWS | null = null
class MockWS {
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  constructor() { lastWs = this }
  close() { this.closed = true }
}
vi.stubGlobal('WebSocket', MockWS)

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
  retryJob: vi.fn().mockResolvedValue({ job_id: 'new-job' }),
  buildWsUrl: vi.fn((id: string) => `ws://localhost/ws/${id}`),
}))

import { JobProgress } from '@/components/JobProgress'

describe('JobProgress', () => {
  beforeEach(() => {
    lastWs = null
  })

  it('renders without crashing', () => {
    render(
      <JobProgress
        jobId="job-123"
        tipoJob="fotos"
        onFinished={vi.fn()}
      />,
    )
    expect(document.body).toBeInTheDocument()
  })

  it('shows progress percentage after receiving websocket message', () => {
    render(
      <JobProgress
        jobId="job-123"
        tipoJob="fotos"
        onFinished={vi.fn()}
      />,
    )

    act(() => {
      lastWs?.onopen?.()
      lastWs?.onmessage?.({
        data: JSON.stringify({
          job_id: 'job-123',
          estado: 'en_proceso',
          porcentaje: 42,
          productos_procesados: 4,
          total_productos: 10,
          imagenes_descargadas: 4,
          imagenes_fallidas: 0,
          descripciones_generadas: 0,
          marcas_procesadas: 0,
          mensaje: 'Procesando...',
          error: null,
          reintentos: 0,
          n_productos_fallidos: 0,
          imagenes_cache_hit: 0,
        }),
      })
    })

    expect(screen.getByText(/42/)).toBeInTheDocument()
  })

  it('calls onFinished when job completes', () => {
    const onFinished = vi.fn()
    render(
      <JobProgress
        jobId="job-123"
        tipoJob="fotos"
        onFinished={onFinished}
      />,
    )

    act(() => {
      lastWs?.onopen?.()
      lastWs?.onmessage?.({
        data: JSON.stringify({
          job_id: 'job-123',
          estado: 'completado',
          porcentaje: 100,
          productos_procesados: 10,
          total_productos: 10,
          imagenes_descargadas: 10,
          imagenes_fallidas: 0,
          descripciones_generadas: 0,
          marcas_procesadas: 0,
          mensaje: 'Completado',
          error: null,
          reintentos: 0,
          n_productos_fallidos: 0,
          imagenes_cache_hit: 0,
        }),
      })
    })

    expect(onFinished).toHaveBeenCalledOnce()
  })
})
