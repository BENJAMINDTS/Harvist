/**
 * Componente de historial de trabajos de scraping.
 *
 * Muestra la lista paginada de todos los jobs registrados en el backend,
 * con filtro por estado, paginación mediante botones Anterior/Siguiente,
 * botón de recarga manual y skeleton de carga animado.
 *
 * @author BenjaminDTS | Carlos Vico
 */
import React, { useCallback, useEffect, useState } from 'react'
import { apiClient } from '@/api/client'
import type { ApiError } from '@/api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EstadoJob = 'pendiente' | 'en_proceso' | 'completado' | 'fallido' | 'cancelado'

interface JobHistoryItem {
  job_id: string
  estado: EstadoJob
  total_productos: number
  imagenes_descargadas: number
  porcentaje: number
  creado_en: string
  completado_en: string | null
  mensaje: string
}

interface JobHistoryData {
  items: JobHistoryItem[]
  total: number
  limit: number
  offset: number
}

interface JobHistoryApiResponse {
  success: boolean
  data: JobHistoryData
  message: string
}

export interface JobHistoryProps {
  /** Callback invocado cuando el usuario selecciona un job de la lista */
  onSelectJob: (jobId: string) => void
}

// ---------------------------------------------------------------------------
// Constantes de presentación
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20

/** Etiqueta y clases Tailwind para cada badge de estado */
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

/** Opciones del selector de filtro de estado */
const ESTADO_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Todos' },
  { value: 'pendiente', label: 'Pendiente' },
  { value: 'en_proceso', label: 'En proceso' },
  { value: 'completado', label: 'Completado' },
  { value: 'fallido', label: 'Fallido' },
  { value: 'cancelado', label: 'Cancelado' },
]

// ---------------------------------------------------------------------------
// Helpers de presentación
// ---------------------------------------------------------------------------

/**
 * Formatea una cadena ISO 8601 en una fecha/hora legible en español.
 *
 * @param iso - Cadena de fecha en formato ISO 8601.
 * @returns Fecha formateada como "DD/MM/YYYY HH:mm".
 */
function formatDate(iso: string): string {
  const d = new Date(iso)
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const year = d.getFullYear()
  const hours = String(d.getHours()).padStart(2, '0')
  const minutes = String(d.getMinutes()).padStart(2, '0')
  return `${day}/${month}/${year} ${hours}:${minutes}`
}

// ---------------------------------------------------------------------------
// Sub-componentes internos
// ---------------------------------------------------------------------------

/** Fila esqueleto animada para el estado de carga */
const SkeletonRow: React.FC = () => (
  <tr className="animate-pulse" aria-hidden="true">
    {Array.from({ length: 6 }).map((_, i) => (
      <td key={i} className="px-4 py-3">
        <div className="h-4 rounded bg-gray-200 dark:bg-gray-700" />
      </td>
    ))}
  </tr>
)

interface EstadoBadgeProps {
  estado: EstadoJob
}

/** Badge de estado coloreado según el valor del job */
const EstadoBadge: React.FC<EstadoBadgeProps> = ({ estado }) => {
  const { label, classes } = ESTADO_BADGE[estado]
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${classes}`}
    >
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

/**
 * Lista paginada del historial de trabajos de scraping.
 *
 * Carga los jobs desde ``GET /api/v1/jobs``, aplica filtrado por estado
 * en el servidor y gestiona la paginación con botones Anterior/Siguiente.
 * Al hacer clic en una fila llama a ``onSelectJob`` con el job_id seleccionado.
 *
 * @param props - Ver ``JobHistoryProps``.
 */
export const JobHistory: React.FC<JobHistoryProps> = ({ onSelectJob }) => {
  // ── Estado interno ─────────────────────────────────────────────────────────
  const [items, setItems] = useState<JobHistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [estadoFiltro, setEstadoFiltro] = useState<string>('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cancellingIds, setCancellingIds] = useState<Set<string>>(new Set())
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())

  // ── Carga de datos ─────────────────────────────────────────────────────────

  /**
   * Solicita la página actual al backend aplicando los filtros activos.
   * Resetea el error antes de cada intento.
   */
  const fetchHistorial = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset,
      }
      if (estadoFiltro !== '') {
        params.estado = estadoFiltro
      }

      const response = await apiClient.get<JobHistoryApiResponse>('/jobs', { params })
      const { data } = response.data

      setItems(data.items)
      setTotal(data.total)
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.message ?? 'Error al cargar el historial.')
      setItems([])
      setTotal(0)
    } finally {
      setIsLoading(false)
    }
  }, [offset, estadoFiltro])

  // Recargar cuando cambia la página o el filtro
  useEffect(() => {
    void fetchHistorial()
  }, [fetchHistorial])

  // ── Handlers ───────────────────────────────────────────────────────────────

  /** Cambia el filtro de estado y vuelve a la primera página */
  const handleEstadoChange = (e: React.ChangeEvent<HTMLSelectElement>): void => {
    setEstadoFiltro(e.target.value)
    setOffset(0)
  }

  const handlePrev = (): void => {
    setOffset((prev) => Math.max(0, prev - PAGE_SIZE))
  }

  const handleNext = (): void => {
    setOffset((prev) => prev + PAGE_SIZE)
  }

  const handleRefresh = (): void => {
    void fetchHistorial()
  }

  /**
   * Cancela un job activo y recarga el historial al confirmar.
   *
   * @param e - Evento del click (necesario para detener la propagación a la fila).
   * @param jobId - Identificador del job a cancelar.
   */
  const handleCancel = async (e: React.MouseEvent, jobId: string): Promise<void> => {
    e.stopPropagation()
    setCancellingIds((prev) => new Set(prev).add(jobId))
    try {
      await apiClient.post(`/jobs/${jobId}/cancel`)
      void fetchHistorial()
    } catch {
      // Silenciar error de UI — el historial se actualizará en el siguiente refresco
    } finally {
      setCancellingIds((prev) => {
        const next = new Set(prev)
        next.delete(jobId)
        return next
      })
    }
  }

  /**
   * Elimina un job del historial llamando a DELETE /jobs/{job_id}.
   *
   * @param e - Evento del click (necesario para detener la propagación a la fila).
   * @param jobId - Identificador del job a eliminar.
   */
  const handleDelete = async (e: React.MouseEvent, jobId: string): Promise<void> => {
    e.stopPropagation()
    setDeletingIds((prev) => new Set(prev).add(jobId))
    try {
      await apiClient.delete(`/jobs/${jobId}`)
      setItems((prev) => prev.filter((item) => item.job_id !== jobId))
      setTotal((prev) => Math.max(0, prev - 1))
    } catch {
      // Silenciar error de UI — el historial se actualizará en el siguiente refresco
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev)
        next.delete(jobId)
        return next
      })
    }
  }

  // ── Derivados de paginación ────────────────────────────────────────────────
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <section
      className="w-full space-y-4"
      aria-label="Historial de trabajos de scraping"
    >
      {/* Cabecera: título, filtro y botón de actualizar */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
          Historial de trabajos
        </h2>

        <div className="flex flex-wrap items-center gap-2">
          {/* Selector de filtro por estado */}
          <label htmlFor="filtro-estado" className="sr-only">
            Filtrar por estado
          </label>
          <select
            id="filtro-estado"
            value={estadoFiltro}
            onChange={handleEstadoChange}
            disabled={isLoading}
            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            aria-label="Filtrar por estado del trabajo"
          >
            {ESTADO_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          {/* Botón de actualizar */}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 shadow-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50"
            aria-label="Recargar historial"
          >
            {isLoading ? (
              <span
                className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-blue-600"
                aria-hidden="true"
              />
            ) : (
              <span aria-hidden="true">↻</span>
            )}
            Actualizar
          </button>
        </div>
      </header>

      {/* Estado de error */}
      {error !== null && (
        <div
          className="flex items-center justify-between gap-3 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-3 text-sm text-red-700 dark:text-red-400"
          role="alert"
          aria-live="assertive"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={handleRefresh}
            className="shrink-0 rounded-md border border-red-300 dark:border-red-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-400 transition-colors hover:bg-red-50 dark:hover:bg-red-950 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Tabla de resultados */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Fecha
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Estado
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Productos
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Imágenes
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Progreso
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-center font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Acciones
              </th>
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-100 dark:divide-gray-700 bg-white dark:bg-gray-900">
            {/* Skeleton de carga: 5 filas animadas */}
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}

            {/* Filas de datos */}
            {!isLoading &&
              items.map((item) => (
                <tr
                  key={item.job_id}
                  onClick={() => onSelectJob(item.job_id)}
                  className="cursor-pointer transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 focus-within:bg-blue-50 dark:focus-within:bg-blue-950"
                  tabIndex={0}
                  role="button"
                  aria-label={`Seleccionar trabajo del ${formatDate(item.creado_en)}, estado: ${ESTADO_BADGE[item.estado].label}`}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelectJob(item.job_id)
                    }
                  }}
                >
                  {/* Fecha de creación */}
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700 dark:text-gray-300">
                    {formatDate(item.creado_en)}
                  </td>

                  {/* Badge de estado */}
                  <td className="px-4 py-3">
                    <EstadoBadge estado={item.estado} />
                  </td>

                  {/* Total de productos */}
                  <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {item.total_productos}
                  </td>

                  {/* Imágenes descargadas */}
                  <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {item.imagenes_descargadas}
                  </td>

                  {/* Barra de progreso + porcentaje */}
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <div className="hidden w-20 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700 sm:block">
                        <div
                          className={`h-2 rounded-full transition-all ${
                            item.estado === 'completado'
                              ? 'bg-green-500'
                              : item.estado === 'fallido'
                              ? 'bg-red-500'
                              : item.estado === 'cancelado'
                              ? 'bg-yellow-500'
                              : item.estado === 'en_proceso'
                              ? 'bg-blue-500'
                              : 'bg-gray-400'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(0, item.porcentaje))}%` }}
                          role="presentation"
                        />
                      </div>
                      <span className="tabular-nums text-gray-600 dark:text-gray-400">
                        {item.porcentaje.toFixed(1)}%
                      </span>
                    </div>
                  </td>

                  {/* Acciones: detener (activos) + borrar (todos) */}
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      {(item.estado === 'pendiente' || item.estado === 'en_proceso') && (
                        <button
                          type="button"
                          onClick={(e) => void handleCancel(e, item.job_id)}
                          disabled={cancellingIds.has(item.job_id)}
                          className="rounded border border-red-300 dark:border-red-700 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-red-600 dark:text-red-400 transition-colors hover:bg-red-50 dark:hover:bg-red-950 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-1 disabled:opacity-50"
                          aria-label={`Detener trabajo del ${formatDate(item.creado_en)}`}
                        >
                          {cancellingIds.has(item.job_id) ? 'Deteniendo…' : 'Detener'}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(e) => void handleDelete(e, item.job_id)}
                        disabled={deletingIds.has(item.job_id)}
                        className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-500 dark:text-gray-400 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-600 dark:hover:border-red-700 dark:hover:bg-red-950 dark:hover:text-red-400 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-1 disabled:opacity-50"
                        aria-label={`Eliminar trabajo del ${formatDate(item.creado_en)}`}
                      >
                        {deletingIds.has(item.job_id) ? '…' : 'Borrar'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}

            {/* Estado vacío */}
            {!isLoading && error === null && items.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-10 text-center text-sm text-gray-500 dark:text-gray-400"
                >
                  No hay trabajos registrados aún.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Controles de paginación */}
      {!isLoading && total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-gray-600 dark:text-gray-400">
          <span>
            Página {currentPage} de {totalPages} — {total} trabajo(s) en total
          </span>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handlePrev}
              disabled={!hasPrev}
              className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2 font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Página anterior"
            >
              Anterior
            </button>
            <button
              type="button"
              onClick={handleNext}
              disabled={!hasNext}
              className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2 font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Página siguiente"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
