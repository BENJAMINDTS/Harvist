/**
 * Componente de seguimiento de progreso de un job de scraping.
 *
 * Muestra en tiempo real el avance del job mediante una conexión WebSocket,
 * incluyendo barra de progreso animada, contadores de imágenes, badge de estado
 * y acciones disponibles al finalizar (descargar ZIP o iniciar nuevo trabajo).
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React, { useEffect, useRef } from 'react'
import { useJobWebSocket } from '@/hooks/useJobWebSocket'
import type { EstadoJob, JobProgressEvent } from '@/hooks/useJobWebSocket'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface JobProgressProps {
  /** UUID del job a monitorizar */
  jobId: string
  /** Llamado cuando el job alcanza un estado terminal (completado o fallido) */
  onFinished: () => void
  /** Llamado cuando el usuario pulsa "Nuevo trabajo" */
  onReset: () => void
}

// ---------------------------------------------------------------------------
// Helpers de presentación
// ---------------------------------------------------------------------------

/** Mapa de colores Tailwind para cada estado del job */
const ESTADO_BADGE: Record<EstadoJob, { label: string; classes: string }> = {
  pendiente: {
    label: 'Pendiente',
    classes: 'bg-gray-100 text-gray-600 border border-gray-300',
  },
  en_proceso: {
    label: 'En proceso',
    classes: 'bg-blue-100 text-blue-700 border border-blue-300',
  },
  completado: {
    label: 'Completado',
    classes: 'bg-green-100 text-green-700 border border-green-300',
  },
  fallido: {
    label: 'Fallido',
    classes: 'bg-red-100 text-red-700 border border-red-300',
  },
  cancelado: {
    label: 'Cancelado',
    classes: 'bg-yellow-100 text-yellow-700 border border-yellow-300',
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
    <div className="h-4 bg-gray-200 rounded w-1/3" />
    <div className="h-3 bg-gray-200 rounded w-full" />
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-16 bg-gray-200 rounded-lg" />
      ))}
    </div>
    <div className="h-8 bg-gray-200 rounded w-2/3 mx-auto" />
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
  <article className="flex flex-col items-center justify-center rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
    <span className={`text-2xl font-bold ${colorClass}`}>{value}</span>
    {total !== undefined && (
      <span className="text-xs text-gray-400">/ {total}</span>
    )}
    <span className="mt-1 text-center text-xs text-gray-500">{label}</span>
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
  onFinished,
  onReset,
}) => {
  const { progress, wsStatus, isFinished } = useJobWebSocket(jobId)

  // Notificar al padre una sola vez cuando el job llega a estado terminal.
  // Se usa ref para evitar llamadas duplicadas en re-renders.
  const finishedNotifiedRef = useRef(false)

  useEffect(() => {
    if (
      isFinished &&
      progress !== null &&
      (progress.estado === 'completado' || progress.estado === 'fallido') &&
      !finishedNotifiedRef.current
    ) {
      finishedNotifiedRef.current = true
      onFinished()
    }
  }, [isFinished, progress, onFinished])

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
    mensaje,
    error,
  } = progress

  const badge = ESTADO_BADGE[estado]
  const progressBarColor = PROGRESS_BAR_COLOR[estado]
  const wsConfig = WS_STATUS_CONFIG[wsStatus]
  const pct = Math.min(100, Math.max(0, Math.round(porcentaje)))
  const downloadUrl = `/api/v1/files/${jobId}`

  // ── Render principal ─────────────────────────────────────────────────────
  return (
    <section
      className="w-full max-w-2xl mx-auto p-4 sm:p-6 space-y-5"
      aria-label="Progreso del trabajo de scraping"
    >
      {/* Cabecera: título + badge de estado */}
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-gray-800">
          Trabajo en curso
        </h2>
        <span
          className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${badge.classes}`}
          role="status"
          aria-label={`Estado del trabajo: ${badge.label}`}
        >
          {badge.label}
        </span>
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
          className="flex justify-between text-xs text-gray-500"
          aria-hidden="true"
        >
          <span>Progreso</span>
          <span>{pct}%</span>
        </div>
        <div
          className="h-3 w-full overflow-hidden rounded-full bg-gray-200"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Progreso del trabajo: ${pct}%`}
        >
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${progressBarColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Mensaje de estado */}
      {mensaje && (
        <p className="text-sm text-gray-600 italic">{mensaje}</p>
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
      </div>

      {/* Mensaje de error cuando el job falla */}
      {estado === 'fallido' && error !== null && (
        <div
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
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
              aria-label="Descargar imágenes en formato ZIP"
            >
              Descargar ZIP
            </a>
          )}
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 shadow-sm transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Nuevo trabajo
          </button>
        </div>
      )}
    </section>
  )
}
