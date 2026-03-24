/**
 * Componente de seguimiento de progreso de un job de scraping.
 *
 * Muestra en tiempo real el avance del job mediante una conexión WebSocket,
 * incluyendo barra de progreso animada, contadores de imágenes, badge de estado
 * y acciones disponibles al finalizar (descargar ZIP o iniciar nuevo trabajo).
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React, { useEffect, useRef, useState } from 'react'
import { useJobWebSocket } from '@/hooks/useJobWebSocket'
import type { EstadoJob } from '@/hooks/useJobWebSocket'
import { apiClient } from '@/api/client'
import type { TipoJob } from '@/components/SearchConfig'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface JobProgressProps {
  /** UUID del job a monitorizar */
  jobId: string
  /** Tipo de trabajo: 'fotos', 'descripciones' o 'marcas'. Controla los contadores mostrados. */
  tipoJob: TipoJob
  /** Llamado cuando el job alcanza un estado terminal (completado o fallido) */
  onFinished: () => void
  /** Llamado cuando el usuario pulsa "Nuevo trabajo" */
  onReset: () => void
  /**
   * Llamado cuando el usuario pulsa "Reanudar" en un job cancelado o fallido.
   * Si no se proporciona, el botón no se muestra.
   */
  onResume?: () => void
}

// ---------------------------------------------------------------------------
// Helpers de presentación
// ---------------------------------------------------------------------------

/** Mapa de colores Tailwind para cada estado del job */
const ESTADO_BADGE: Record<EstadoJob, { label: string; classes: string }> = {
  pendiente: {
    label: 'Pendiente',
    classes: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600',
  },
  en_proceso: {
    label: 'En proceso',
    classes: 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400 border border-blue-300 dark:border-blue-700',
  },
  completado: {
    label: 'Completado',
    classes: 'bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-400 border border-green-300 dark:border-green-800',
  },
  fallido: {
    label: 'Fallido',
    classes: 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-400 border border-red-300 dark:border-red-800',
  },
  cancelado: {
    label: 'Cancelado',
    classes: 'bg-yellow-100 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-400 border border-yellow-300 dark:border-yellow-800',
  },
}

/** Mapa de colores para la barra de progreso según estado del job */
const PROGRESS_BAR_COLOR: Record<EstadoJob, string> = {
  pendiente: 'bg-gray-400',
  en_proceso: 'bg-blue-500',
  completado: 'bg-green-500',
  fallido: 'bg-red-500',
  cancelado: 'bg-yellow-500',
}

/** Configuración visual del indicador de estado del WebSocket */
const WS_STATUS_CONFIG: Record<
  'connecting' | 'connected' | 'reconnecting' | 'closed' | 'error',
  { label: string; dotClass: string; textClass: string }
> = {
  connecting: {
    label: 'Conectando…',
    dotClass: 'bg-yellow-400 animate-pulse',
    textClass: 'text-yellow-600',
  },
  connected: {
    label: 'Conectado',
    dotClass: 'bg-green-500',
    textClass: 'text-green-600',
  },
  reconnecting: {
    label: 'Reconectando…',
    dotClass: 'bg-orange-400 animate-pulse',
    textClass: 'text-orange-600',
  },
  closed: {
    label: 'Desconectado',
    dotClass: 'bg-gray-400',
    textClass: 'text-gray-500',
  },
  error: {
    label: 'Error de conexión',
    dotClass: 'bg-red-500',
    textClass: 'text-red-600',
  },
}

// ---------------------------------------------------------------------------
// Iconos SVG inline
// ---------------------------------------------------------------------------

interface IconProps {
  className?: string
}

/**
 * Icono de reanudar/reproducir (flecha circular) para el botón de reanudación.
 */
const ResumeIcon: React.FC<IconProps> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.5}
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
    />
  </svg>
)

// ---------------------------------------------------------------------------
// Sub-componentes internos
// ---------------------------------------------------------------------------

/**
 * Esqueleto de carga que se muestra mientras no se han recibido datos del WS.
 */
const ProgressSkeleton: React.FC = () => (
  <div
    className="animate-pulse space-y-4"
    role="status"
    aria-label="Cargando datos del trabajo…"
  >
    <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3" />
    <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded-lg" />
      ))}
    </div>
    <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-2/3 mx-auto" />
  </div>
)

// ---------------------------------------------------------------------------
// Tipos auxiliares para las props de CounterCard
// ---------------------------------------------------------------------------

interface CounterCardProps {
  label: string
  value: number
  total?: number
  colorClass: string
}

/**
 * Tarjeta de contador individual para métricas del job.
 */
const CounterCard: React.FC<CounterCardProps> = ({
  label,
  value,
  total,
  colorClass,
}) => (
  <article className="flex flex-col items-center justify-center rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-3 shadow-sm">
    <span className={`text-2xl font-bold ${colorClass}`}>{value}</span>
    {total !== undefined && (
      <span className="text-xs text-gray-400 dark:text-gray-500">/ {total}</span>
    )}
    <span className="mt-1 text-center text-xs text-gray-500 dark:text-gray-400">{label}</span>
  </article>
)

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

/**
 * Muestra el progreso en tiempo real de un job de scraping de imágenes.
 *
 * Se conecta al WebSocket del job indicado, actualiza la UI de forma reactiva
 * y notifica al padre cuando el job finaliza o el usuario solicita reinicio.
 *
 * @param props - Ver `JobProgressProps`.
 */
export const JobProgress: React.FC<JobProgressProps> = ({
  jobId,
  tipoJob,
  onFinished,
  onReset,
  onResume,
}) => {
  const { progress, wsStatus, isFinished } = useJobWebSocket(jobId)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  // Notificar al padre una sola vez cuando el job llega a estado terminal.
  // Se usa ref para evitar llamadas duplicadas en re-renders.
  const finishedNotifiedRef = useRef(false)

  useEffect(() => {
    if (
      isFinished &&
      progress !== null &&
      (progress.estado === 'completado' || progress.estado === 'fallido' || progress.estado === 'cancelado') &&
      !finishedNotifiedRef.current
    ) {
      finishedNotifiedRef.current = true
      onFinished()
    }
  }, [isFinished, progress, onFinished])

  /** Envía la solicitud de cancelación al backend */
  const handleCancel = async (): Promise<void> => {
    setCancelling(true)
    setCancelError(null)
    try {
      await apiClient.post(`/jobs/${jobId}/cancel`)
    } catch (err: unknown) {
      const apiErr = err as { message?: string; status?: number }
      setCancelError(apiErr.message ?? 'No se pudo cancelar el trabajo.')
    } finally {
      setCancelling(false)
    }
  }

  // ── Skeleton mientras no hay datos ──────────────────────────────────────
  if (progress === null) {
    return (
      <section className="w-full max-w-2xl mx-auto p-4 sm:p-6">
        <ProgressSkeleton />
      </section>
    )
  }

  // ── Variables de presentación ────────────────────────────────────────────
  const {
    estado,
    porcentaje,
    productos_procesados,
    total_productos,
    imagenes_descargadas,
    imagenes_fallidas,
    descripciones_generadas,
    marcas_procesadas,
    mensaje,
    error,
  } = progress

  const badge = ESTADO_BADGE[estado]
  const progressBarColor = PROGRESS_BAR_COLOR[estado]
  const wsConfig = WS_STATUS_CONFIG[wsStatus]
  const pct = Math.min(100, Math.max(0, Math.round(porcentaje)))
  const downloadUrl = tipoJob === 'descripciones'
    ? `/api/v1/files/${jobId}/csv`
    : tipoJob === 'marcas'
    ? `/api/v1/files/${jobId}/brands`
    : `/api/v1/files/${jobId}`

  // ── Render principal ─────────────────────────────────────────────────────
  return (
    <section
      className="w-full max-w-2xl mx-auto p-4 sm:p-6 space-y-5"
      aria-label="Progreso del trabajo de scraping"
    >
      {/* Cabecera: título + badge de estado + botón detener */}
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
          Trabajo en curso
        </h2>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${badge.classes}`}
            role="status"
            aria-label={`Estado del trabajo: ${badge.label}`}
          >
            {badge.label}
          </span>
          {(estado === 'pendiente' || estado === 'en_proceso') && (
            <button
              type="button"
              onClick={() => void handleCancel()}
              disabled={cancelling}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 dark:border-red-700 bg-white dark:bg-gray-800 px-3 py-1 text-sm font-medium text-red-600 dark:text-red-400 transition-colors hover:bg-red-50 dark:hover:bg-red-950 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-2 disabled:opacity-50"
              aria-label="Detener este trabajo"
            >
              {cancelling ? 'Deteniendo…' : 'Detener'}
            </button>
          )}
        </div>
      </header>

      {/* Indicador de conexión WebSocket */}
      <div className="flex items-center gap-2 text-sm">
        <span
          className={`inline-block h-2 w-2 rounded-full ${wsConfig.dotClass}`}
          aria-hidden="true"
        />
        <span className={wsConfig.textClass}>{wsConfig.label}</span>
      </div>

      {/* Barra de progreso */}
      <div className="space-y-1">
        <div
          className="flex justify-between text-xs text-gray-500 dark:text-gray-400"
          aria-hidden="true"
        >
          <span>Progreso</span>
          <span>{pct}%</span>
        </div>
        {/* progress nativo: semánticamente correcto, oculto visualmente */}
        <progress
          className="sr-only"
          value={pct}
          max={100}
          aria-label={`Progreso del trabajo: ${pct}%`}
        />
        {/* Barra decorativa */}
        <div className="h-3 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700" aria-hidden="true">
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${progressBarColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Mensaje de estado */}
      {mensaje && (
        <p className="text-sm text-gray-600 dark:text-gray-400 italic">{mensaje}</p>
      )}

      {/* Tarjetas de contadores */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CounterCard
          label="Procesados"
          value={productos_procesados}
          total={total_productos}
          colorClass="text-blue-600"
        />
        <CounterCard
          label="Total productos"
          value={total_productos}
          colorClass="text-gray-700"
        />
        {tipoJob === 'descripciones' ? (
          <>
            <CounterCard
              label="Descripciones OK"
              value={descripciones_generadas}
              colorClass="text-green-600"
            />
            <CounterCard
              label="Desc. fallidas"
              value={Math.max(0, productos_procesados - descripciones_generadas)}
              colorClass="text-red-500"
            />
          </>
        ) : tipoJob === 'marcas' ? (
          <>
            <CounterCard
              label="Marcas OK"
              value={marcas_procesadas}
              colorClass="text-green-600"
            />
            <CounterCard
              label="Marcas fallidas"
              value={Math.max(0, productos_procesados - marcas_procesadas)}
              colorClass="text-red-500"
            />
          </>
        ) : (
          <>
            <CounterCard
              label="Imágenes OK"
              value={imagenes_descargadas}
              colorClass="text-green-600"
            />
            <CounterCard
              label="Imágenes fallidas"
              value={imagenes_fallidas}
              colorClass="text-red-500"
            />
          </>
        )}
      </div>

      {/* Error al intentar cancelar */}
      {cancelError !== null && (
        <div className="rounded border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 px-3 py-2 text-sm text-red-700 dark:text-red-400" role="alert">
          {cancelError}
        </div>
      )}

      {/* Mensaje de error cuando el job falla */}
      {estado === 'fallido' && error !== null && (
        <div
          className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-3 text-sm text-red-700 dark:text-red-400"
          role="alert"
          aria-live="assertive"
        >
          <span className="font-medium">Error: </span>
          {error}
        </div>
      )}

      {/* Acciones disponibles al finalizar */}
      {isFinished && (
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          {estado === 'completado' && (
            <a
              href={downloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-green-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
              aria-label={
                tipoJob === 'descripciones'
                  ? 'Descargar descripciones en formato CSV'
                  : tipoJob === 'marcas'
                  ? 'Descargar fichas de marca en formato JSON'
                  : 'Descargar imágenes en formato ZIP'
              }
            >
              {tipoJob === 'descripciones'
                ? 'Descargar descripciones'
                : tipoJob === 'marcas'
                ? 'Descargar marcas.json'
                : 'Descargar ZIP'}
            </a>
          )}
          {(estado === 'cancelado' || estado === 'fallido') && onResume !== undefined && (
            <button
              type="button"
              onClick={onResume}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-400 dark:border-blue-700 bg-white dark:bg-gray-800 px-5 py-2.5 text-sm font-semibold text-blue-700 dark:text-blue-400 shadow-sm transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              aria-label="Reanudar este trabajo desde donde se detuvo"
            >
              <ResumeIcon className="h-4 w-4" />
              Reanudar
            </button>
          )}
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-5 py-2.5 text-sm font-semibold text-gray-700 dark:text-gray-300 shadow-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Nuevo trabajo
          </button>
        </div>
      )}
    </section>
  )
}
