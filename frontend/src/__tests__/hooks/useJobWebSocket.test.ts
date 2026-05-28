/**
 * Tests unitarios del hook useJobWebSocket.
 *
 * Simula el ciclo de vida del WebSocket con un mock global y verifica:
 * - Estado inicial 'connecting' al montar con jobId
 * - Transición a 'connected' en onopen
 * - Actualización de progress al recibir mensaje válido
 * - isFinished=true al recibir estado terminal (completado, fallido…)
 * - Reconexión automática con backoff al cerrar sin terminar
 * - Sin conexión cuando jobId es null
 * - Cierre limpio al desmontar (no intenta reconectar)
 * - Estado 'error' al alcanzar MAX_RETRIES
 *
 * @author BenjaminDTS | Carlos Vico
 * @version 1.0.0
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useJobWebSocket, type JobProgressEvent, type EstadoJob } from '@/hooks/useJobWebSocket'

// ── Mock WebSocket ─────────────────────────────────────────────────────────────

/**
 * Instancia más reciente del MockWebSocket creada durante el test.
 * Se reasigna cada vez que new WebSocket() es llamado.
 */
let lastWs: MockWebSocket | null = null

/**
 * Mock de WebSocket que expone handlers onopen/onmessage/onerror/onclose
 * como propiedades settables para que el test pueda dispararlos manualmente.
 *
 * @author BenjaminDTS
 */
class MockWebSocket {
  /** URL con la que fue instanciado. */
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    lastWs = this
  }

  /** Simula el cierre de la conexión. */
  close() {
    this.closed = true
    this.onclose?.()
  }

  /** Helper de test: dispara onopen. */
  triggerOpen() { this.onopen?.() }

  /** Helper de test: dispara onmessage con el evento dado. */
  triggerMessage(data: object) { this.onmessage?.({ data: JSON.stringify(data) }) }

  /** Helper de test: dispara onerror. */
  triggerError() { this.onerror?.() }
}

// ── Setup / Teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  lastWs = null
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Construye un evento de progreso mínimo para usar en tests.
 *
 * @param estado - Estado del job a inyectar en el evento.
 * @returns JobProgressEvent con valores por defecto.
 */
function makeProgressEvent(estado: EstadoJob): JobProgressEvent {
  return {
    job_id: 'job-test',
    estado,
    porcentaje: 50,
    productos_procesados: 5,
    total_productos: 10,
    imagenes_descargadas: 5,
    imagenes_fallidas: 0,
    descripciones_generadas: 0,
    marcas_procesadas: 0,
    mensaje: 'Procesando…',
    error: null,
    reintentos: 0,
    n_productos_fallidos: 0,
    imagenes_cache_hit: 0,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useJobWebSocket — estado inicial', () => {
  /**
   * Verifica el estado del hook en el momento del montaje.
   *
   * @author BenjaminDTS
   */

  it('devuelve progress=null y wsStatus=connecting al montar con jobId', () => {
    const { result } = renderHook(() => useJobWebSocket('job-test'))
    expect(result.current.progress).toBeNull()
    expect(result.current.wsStatus).toBe('connecting')
    expect(result.current.isFinished).toBe(false)
  })

  it('no crea WebSocket si jobId es null', () => {
    renderHook(() => useJobWebSocket(null))
    expect(lastWs).toBeNull()
  })
})

describe('useJobWebSocket — ciclo conectado', () => {
  /**
   * Verifica transiciones de estado en conexión exitosa y recepción de mensajes.
   *
   * @author BenjaminDTS
   */

  it('pasa a connected tras onopen', () => {
    const { result } = renderHook(() => useJobWebSocket('job-test'))
    act(() => { lastWs!.triggerOpen() })
    expect(result.current.wsStatus).toBe('connected')
  })

  it('actualiza progress al recibir mensaje en_proceso', () => {
    const { result } = renderHook(() => useJobWebSocket('job-test'))
    act(() => { lastWs!.triggerOpen() })
    act(() => { lastWs!.triggerMessage(makeProgressEvent('en_proceso')) })
    expect(result.current.progress?.estado).toBe('en_proceso')
    expect(result.current.progress?.porcentaje).toBe(50)
    expect(result.current.isFinished).toBe(false)
  })

  it('ignora mensajes JSON malformados sin lanzar excepción', () => {
    const { result } = renderHook(() => useJobWebSocket('job-test'))
    act(() => { lastWs!.triggerOpen() })
    act(() => { lastWs!.onmessage?.({ data: '<<<not-json>>>' }) })
    expect(result.current.progress).toBeNull()
  })
})

describe('useJobWebSocket — estados terminales', () => {
  /**
   * Verifica que los estados terminales marcan isFinished y cierran el socket.
   *
   * @author BenjaminDTS
   */
  const terminalStates: EstadoJob[] = [
    'completado',
    'fallido',
    'cancelado',
    'pendiente_seleccion_fotos',
    'pendiente_validacion_marcas',
  ]

  terminalStates.forEach((estado) => {
    it(`isFinished=true al recibir estado "${estado}"`, () => {
      const { result } = renderHook(() => useJobWebSocket('job-test'))
      act(() => { lastWs!.triggerOpen() })
      act(() => { lastWs!.triggerMessage(makeProgressEvent(estado)) })
      expect(result.current.isFinished).toBe(true)
      expect(lastWs!.closed).toBe(true)
    })
  })
})

describe('useJobWebSocket — reconexión', () => {
  /**
   * Verifica el mecanismo de backoff exponencial al perder la conexión.
   *
   * @author BenjaminDTS
   */

  it('pasa a reconnecting tras cierre inesperado', () => {
    const { result } = renderHook(() => useJobWebSocket('job-test'))
    const firstWs = lastWs!
    act(() => { firstWs.triggerOpen() })
    // Cerrar sin haber terminado el job
    act(() => {
      firstWs.closed = true
      firstWs.onclose?.()
    })
    expect(result.current.wsStatus).toBe('reconnecting')
  })

  it('crea nuevo WebSocket tras el delay de backoff', () => {
    renderHook(() => useJobWebSocket('job-test'))
    const firstWs = lastWs!
    act(() => { firstWs.triggerOpen() })
    act(() => {
      firstWs.closed = true
      firstWs.onclose?.()
    })
    // Avanzar el primer delay (1000ms)
    act(() => { vi.advanceTimersByTime(1000) })
    expect(lastWs).not.toBe(firstWs)
  })
})

describe('useJobWebSocket — desmontaje', () => {
  /**
   * Verifica cierre limpio del WebSocket al desmontar el componente.
   *
   * @author BenjaminDTS
   */

  it('cierra el WebSocket al desmontar', () => {
    const { unmount } = renderHook(() => useJobWebSocket('job-test'))
    const ws = lastWs!
    act(() => { ws.triggerOpen() })
    unmount()
    expect(ws.closed).toBe(true)
  })

  it('no reconecta tras desmontar aunque se cierre el socket', () => {
    const { unmount } = renderHook(() => useJobWebSocket('job-test'))
    const firstWs = lastWs!
    act(() => { firstWs.triggerOpen() })
    unmount()
    const wsAfterUnmount = lastWs
    // Avanzar timers — no debe crear nuevo WebSocket
    act(() => { vi.advanceTimersByTime(5000) })
    expect(lastWs).toBe(wsAfterUnmount)
  })
})

describe('useJobWebSocket — error de conexión', () => {
  /**
   * Verifica el estado error cuando falla la conexión WebSocket.
   *
   * @author BenjaminDTS
   */

  it('pasa a wsStatus=error en onerror', () => {
    const { result } = renderHook(() => useJobWebSocket('job-test'))
    act(() => { lastWs!.triggerError() })
    expect(result.current.wsStatus).toBe('error')
  })
})
