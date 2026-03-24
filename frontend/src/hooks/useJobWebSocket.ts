/**
 * Hook que gestiona la conexión WebSocket de progreso de un job.
 *
 * Características:
 * - Reconexión automática con backoff exponencial (máx. 5 intentos)
 * - Cierre limpio al desmontar el componente o al terminar el job
 * - Tipado estricto del evento de progreso alineado con JobProgressEvent del backend
 *
 * @author BenjaminDTS | Carlos Vico
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { buildWsUrl } from '@/api/client'

/** Estados posibles del job, espejados desde EstadoJob del backend */
export type EstadoJob =
  | 'pendiente'
  | 'en_proceso'
  | 'completado'
  | 'fallido'
  | 'cancelado'

/** Evento de progreso emitido por el WebSocket del backend */
export interface JobProgressEvent {
  job_id: string
  estado: EstadoJob
  porcentaje: number
  productos_procesados: number
  total_productos: number
  imagenes_descargadas: number
  imagenes_fallidas: number
  descripciones_generadas: number
  marcas_procesadas: number
  mensaje: string
  error: string | null
}

/** Estados internos de la conexión WebSocket */
type WsStatus = 'connecting' | 'connected' | 'reconnecting' | 'closed' | 'error'

interface UseJobWebSocketReturn {
  /** Último evento de progreso recibido, o null si aún no hay datos */
  progress: JobProgressEvent | null
  /** Estado de la conexión WebSocket */
  wsStatus: WsStatus
  /** True cuando el job ha terminado (completado, fallido o cancelado) */
  isFinished: boolean
}

const MAX_RETRIES = 5
const BASE_DELAY_MS = 1_000
const FINISHED_STATES: EstadoJob[] = ['completado', 'fallido', 'cancelado']

/**
 * Conecta al WebSocket de progreso de un job y devuelve el estado reactivo.
 *
 * @param jobId - UUID del job a monitorizar. Si es null, no conecta.
 * @returns Objeto con el último evento, estado de conexión y flag de fin.
 */
export function useJobWebSocket(jobId: string | null): UseJobWebSocketReturn {
  const [progress, setProgress] = useState<JobProgressEvent | null>(null)
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting')
  const [isFinished, setIsFinished] = useState(false)

  // Refs para valores que no deben disparar re-renders
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Flag para saber si el desmontaje fue intencional (evita reconexión)
  const unmountedRef = useRef(false)

  const connect = useCallback(() => {
    if (!jobId || unmountedRef.current) return

    setWsStatus(retriesRef.current === 0 ? 'connecting' : 'reconnecting')

    const url = buildWsUrl(jobId)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      retriesRef.current = 0
      setWsStatus('connected')
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as JobProgressEvent

        // El backend puede enviar un objeto de error no tipado como JobProgressEvent
        if ('error' in data && typeof (data as { error?: string }).error === 'string' && !data.job_id) {
          setWsStatus('error')
          setIsFinished(true)
          ws.close()
          return
        }

        setProgress(data)

        if (FINISHED_STATES.includes(data.estado)) {
          setIsFinished(true)
          setWsStatus('closed')
          ws.close()
        }
      } catch {
        // Mensaje malformado — ignorar silenciosamente
      }
    }

    ws.onerror = () => {
      setWsStatus('error')
    }

    ws.onclose = () => {
      if (unmountedRef.current || isFinished) return

      if (retriesRef.current < MAX_RETRIES) {
        // Backoff exponencial: 1s, 2s, 4s, 8s, 16s
        const delay = BASE_DELAY_MS * Math.pow(2, retriesRef.current)
        retriesRef.current += 1
        setWsStatus('reconnecting')
        timeoutRef.current = setTimeout(connect, delay)
      } else {
        setWsStatus('error')
      }
    }
  }, [jobId, isFinished])

  useEffect(() => {
    unmountedRef.current = false
    connect()

    return () => {
      unmountedRef.current = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [connect])

  return { progress, wsStatus, isFinished }
}
