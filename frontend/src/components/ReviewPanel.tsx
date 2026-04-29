/**
 * Panel de revisión manual de descripciones generadas por IA.
 *
 * Permite aprobar, rechazar o editar cada descripción antes de exportar.
 * Incluye edición inline (blur/Enter confirma, Escape cancela), tabs de filtro,
 * paginación y aprobación masiva.
 *
 * @author Carlitos6712
 * @param jobId      - Identificador del job a revisar.
 * @param onComplete - Callback llamado cuando todas las revisiones están hechas.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { apiClient } from '@/api/client'

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface ReviewEntry {
  codigo: string
  nombre: string
  descripcion_corta: string
  descripcion_larga: string
  status: 'pending' | 'approved' | 'rejected'
  edited_text: string | null
}

interface ReviewPanelProps {
  jobId: string
  onComplete: () => void
}

interface ApiReviewItem {
  codigo: string
  nombre: string
  descripcion_corta: string
  descripcion_larga: string
  status: 'pending' | 'approved' | 'rejected'
  edited_text: string | null
}

interface ApiReviewResponse {
  success: boolean
  data: {
    items: ApiReviewItem[]
    total: number
    limit: number
    offset: number
  }
}

interface ApiPatchResponse {
  success: boolean
  data: {
    codigo: string
    status: 'pending' | 'approved' | 'rejected'
    edited_text: string | null
  }
}

// ─── Constantes ───────────────────────────────────────────────────────────────

const PAGE_SIZE = 25
type TabFilter = 'all' | 'pending' | 'approved' | 'rejected'

const STATUS_CONFIG: Record<
  'pending' | 'approved' | 'rejected',
  { label: string; classes: string }
> = {
  pending: {
    label: 'Pendiente',
    classes: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  },
  approved: {
    label: 'Aprobada',
    classes: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  },
  rejected: {
    label: 'Rechazada',
    classes: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  },
}

// ─── Componente ───────────────────────────────────────────────────────────────

export const ReviewPanel: React.FC<ReviewPanelProps> = ({ jobId, onComplete }) => {
  const [entries, setEntries] = useState<ReviewEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabFilter>('all')
  const [page, setPage] = useState(0)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [editingCodigo, setEditingCodigo] = useState<string | null>(null)
  const [editingText, setEditingText] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const confirmingRef = useRef(false)

  // ── Carga de datos ───────────────────────────────────────────────────────────

  const cargarEntradas = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const allItems: ReviewEntry[] = []
      let offset = 0
      const limit = 100

      while (true) {
        const response = await apiClient.get<ApiReviewResponse>(
          `/jobs/${jobId}/descriptions/review`,
          { params: { limit, offset } }
        )
        const { items, total } = response.data.data
        allItems.push(...items)
        offset += items.length
        if (allItems.length >= total || items.length === 0) break
      }

      setEntries(allItems)
    } catch {
      setLoadError('No se pudieron cargar las descripciones.')
    } finally {
      setLoading(false)
    }
  }, [jobId])

  useEffect(() => {
    cargarEntradas()
  }, [cargarEntradas])

  useEffect(() => {
    if (editingCodigo && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [editingCodigo])

  // ── Acciones de revisión ─────────────────────────────────────────────────────

  const aplicarAccion = useCallback(
    async (
      codigo: string,
      action: 'approve' | 'reject' | 'edit',
      editedText?: string
    ): Promise<void> => {
      setActionLoading(codigo)
      setActionError(null)
      try {
        const body: { action: string; edited_text?: string } = { action }
        if (action === 'edit' && editedText !== undefined) {
          body.edited_text = editedText
        }

        const response = await apiClient.patch<ApiPatchResponse>(
          `/jobs/${jobId}/descriptions/${encodeURIComponent(codigo)}`,
          body
        )
        const { status: newStatus, edited_text: newEditedText } = response.data.data

        setEntries((prev) =>
          prev.map((e) =>
            e.codigo === codigo
              ? {
                  ...e,
                  status: newStatus,
                  edited_text: newEditedText,
                  descripcion_corta:
                    action === 'edit' && newEditedText ? newEditedText : e.descripcion_corta,
                }
              : e
          )
        )
      } catch {
        setActionError('No se pudo guardar la revisión. Inténtalo de nuevo.')
      } finally {
        setActionLoading(null)
      }
    },
    [jobId]
  )

  const handleApprove = useCallback(
    (codigo: string) => aplicarAccion(codigo, 'approve'),
    [aplicarAccion]
  )

  const handleReject = useCallback(
    (codigo: string) => aplicarAccion(codigo, 'reject'),
    [aplicarAccion]
  )

  const handleStartEdit = useCallback((entry: ReviewEntry) => {
    setEditingCodigo(entry.codigo)
    setEditingText(entry.descripcion_corta)
  }, [])

  const handleConfirmEdit = useCallback(
    async (codigo: string) => {
      if (confirmingRef.current) return
      confirmingRef.current = true
      try {
        if (editingText.trim()) {
          await aplicarAccion(codigo, 'edit', editingText.trim())
        }
        setEditingCodigo(null)
        setEditingText('')
      } finally {
        confirmingRef.current = false
      }
    },
    [aplicarAccion, editingText]
  )

  const handleCancelEdit = useCallback(() => {
    setEditingCodigo(null)
    setEditingText('')
  }, [])

  const handleKeyDownEdit = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>, codigo: string) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleConfirmEdit(codigo)
      } else if (e.key === 'Escape') {
        handleCancelEdit()
      }
    },
    [handleConfirmEdit, handleCancelEdit]
  )

  // ── Aprobación masiva ────────────────────────────────────────────────────────

  const handleAprobarTodas = useCallback(async () => {
    const pendientes = entries.filter((e) => e.status === 'pending')
    for (const entry of pendientes) {
      await aplicarAccion(entry.codigo, 'approve')
    }
  }, [entries, aplicarAccion])

  // ── Exportar aprobadas ───────────────────────────────────────────────────────

  const handleExportarAprobadas = useCallback(async () => {
    setExportLoading(true)
    setExportError(null)
    try {
      const response = await apiClient.get<Blob>(
        `/files/${jobId}/csv`,
        { params: { only_approved: true }, responseType: 'blob' }
      )
      if (response.status === 204) {
        setExportError('No hay descripciones aprobadas para exportar.')
        return
      }
      const url = URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `descripciones_aprobadas_${jobId.slice(0, 8)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setExportError('Error al descargar el CSV de aprobadas.')
    } finally {
      setExportLoading(false)
    }
  }, [jobId])

  // ── Filtrado y paginación ────────────────────────────────────────────────────

  const entradaFiltradas: ReviewEntry[] = entries.filter((e) => {
    if (activeTab === 'all') return true
    return e.status === activeTab
  })

  const totalPaginas = Math.max(1, Math.ceil(entradaFiltradas.length / PAGE_SIZE))
  const paginaActual = Math.min(page, totalPaginas - 1)
  const entradasPagina = entradaFiltradas.slice(
    paginaActual * PAGE_SIZE,
    (paginaActual + 1) * PAGE_SIZE
  )

  const revisadas = entries.filter((e) => e.status !== 'pending').length
  const aprobadas = entries.filter((e) => e.status === 'approved').length
  const pendientes = entries.filter((e) => e.status === 'pending').length

  const handleTabChange = useCallback((tab: TabFilter) => {
    setActiveTab(tab)
    setPage(0)
  }, [])

  // ── Render: estados especiales ───────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-gray-500 dark:text-gray-400">
        <svg
          className="mr-2 h-4 w-4 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
        Cargando revisiones…
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 px-4 py-3 text-sm text-red-700 dark:text-red-400" role="alert">
        {loadError}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
        Este job no generó descripciones.
      </p>
    )
  }

  // ── Render: panel completo ───────────────────────────────────────────────────

  const TABS: { key: TabFilter; label: string; count: number }[] = [
    { key: 'all', label: 'Todas', count: entries.length },
    { key: 'pending', label: 'Pendientes', count: pendientes },
    { key: 'approved', label: 'Aprobadas', count: aprobadas },
    { key: 'rejected', label: 'Rechazadas', count: entries.filter((e) => e.status === 'rejected').length },
  ]

  return (
    <div className="flex flex-col gap-4">
      {/* ── Barra superior ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {revisadas} / {entries.length} revisadas
        </span>

        <div className="flex items-center gap-2">
          {pendientes > 0 && (
            <button
              type="button"
              onClick={handleAprobarTodas}
              disabled={actionLoading !== null}
              className={
                "px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors duration-150 " +
                "bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 " +
                "text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 " +
                "disabled:opacity-50 disabled:cursor-not-allowed"
              }
            >
              Aprobar todas ({pendientes})
            </button>
          )}

          <button
            type="button"
            onClick={handleExportarAprobadas}
            disabled={aprobadas === 0 || exportLoading}
            aria-disabled={aprobadas === 0}
            className={
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors duration-150 " +
              (aprobadas > 0
                ? "bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700 text-green-700 dark:text-green-300 hover:bg-green-100 dark:hover:bg-green-900/40"
                : "bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-400 cursor-not-allowed") +
              " disabled:opacity-50 disabled:cursor-not-allowed"
            }
          >
            {exportLoading ? (
              <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            ) : (
              <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path d="M8 12l-4.5-4.5 1.06-1.06L7 9.38V2h2v7.38l2.44-2.94 1.06 1.06L8 12zM2 14h12v-2H2v2z" />
              </svg>
            )}
            Exportar aprobadas
          </button>
        </div>
      </div>

      {exportError && (
        <p className="text-xs text-red-600 dark:text-red-400" role="alert">{exportError}</p>
      )}

      {actionError && (
        <p className="text-xs text-red-600 dark:text-red-400" role="alert">{actionError}</p>
      )}

      {/* ── Tabs de filtro ── */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700" role="tablist">
        {TABS.map(({ key, label, count }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={activeTab === key}
            onClick={() => handleTabChange(key)}
            className={
              "px-3 py-2 text-xs font-medium border-b-2 transition-colors duration-150 " +
              (activeTab === key
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300")
            }
          >
            {label}
            <span
              className={
                "ml-1.5 rounded-full px-1.5 py-0.5 text-xs " +
                (activeTab === key
                  ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                  : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400")
              }
            >
              {count}
            </span>
          </button>
        ))}
      </div>

      {/* ── Tabla ── */}
      {entradasPagina.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
          No hay descripciones en esta categoría.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 text-left w-24">Código</th>
                <th className="px-3 py-2 text-left w-32">Nombre</th>
                <th className="px-3 py-2 text-left">Descripción corta</th>
                <th className="px-3 py-2 text-left hidden lg:table-cell">Descripción larga</th>
                <th className="px-3 py-2 text-left w-24">Estado</th>
                <th className="px-3 py-2 text-right w-28">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-900">
              {entradasPagina.map((entry) => {
                const isEditing = editingCodigo === entry.codigo
                const isLoading = actionLoading === entry.codigo
                const statusCfg = STATUS_CONFIG[entry.status]

                return (
                  <tr
                    key={entry.codigo}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                  >
                    <td className="px-3 py-2 font-mono text-xs text-gray-500 dark:text-gray-400 align-top">
                      {entry.codigo}
                    </td>
                    <td className="px-3 py-2 text-gray-800 dark:text-gray-200 align-top">
                      {entry.nombre}
                    </td>
                    <td
                      className="px-3 py-2 align-top cursor-pointer"
                      onClick={() => !isEditing && handleStartEdit(entry)}
                      title="Click para editar"
                    >
                      {isEditing ? (
                        <textarea
                          ref={textareaRef}
                          value={editingText}
                          onChange={(e) => setEditingText(e.target.value)}
                          onBlur={() => handleConfirmEdit(entry.codigo)}
                          onKeyDown={(e) => handleKeyDownEdit(e, entry.codigo)}
                          rows={3}
                          className={
                            "w-full rounded border border-blue-400 dark:border-blue-500 bg-white dark:bg-gray-800 " +
                            "px-2 py-1 text-sm text-gray-800 dark:text-gray-100 " +
                            "focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                          }
                          aria-label={`Editar descripción corta de ${entry.codigo}`}
                        />
                      ) : (
                        <span className="text-gray-700 dark:text-gray-300 line-clamp-2 hover:line-clamp-none">
                          {entry.edited_text ?? entry.descripcion_corta}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-gray-600 dark:text-gray-400 align-top text-xs hidden lg:table-cell">
                      <span className="line-clamp-3">{entry.descripcion_larga}</span>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <span
                        className={
                          "inline-block rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap " +
                          statusCfg.classes
                        }
                      >
                        {statusCfg.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 align-top text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => handleApprove(entry.codigo)}
                          disabled={entry.status === 'approved' || isLoading}
                          aria-label={`Aprobar descripción de ${entry.codigo}`}
                          title="Aprobar"
                          className={
                            "rounded p-1 transition-colors duration-150 " +
                            (entry.status === 'approved' || isLoading
                              ? "text-gray-300 dark:text-gray-600 cursor-not-allowed"
                              : "text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20")
                          }
                        >
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <path
                              fillRule="evenodd"
                              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                              clipRule="evenodd"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReject(entry.codigo)}
                          disabled={entry.status === 'rejected' || isLoading}
                          aria-label={`Rechazar descripción de ${entry.codigo}`}
                          title="Rechazar"
                          className={
                            "rounded p-1 transition-colors duration-150 " +
                            (entry.status === 'rejected' || isLoading
                              ? "text-gray-300 dark:text-gray-600 cursor-not-allowed"
                              : "text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20")
                          }
                        >
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <path
                              fillRule="evenodd"
                              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                              clipRule="evenodd"
                            />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Paginación ── */}
      {totalPaginas > 1 && (
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>
            {paginaActual * PAGE_SIZE + 1}–
            {Math.min((paginaActual + 1) * PAGE_SIZE, entradaFiltradas.length)}{' '}
            de {entradaFiltradas.length}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              disabled={paginaActual === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="rounded px-2 py-1 border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800"
              aria-label="Página anterior"
            >
              ‹
            </button>
            <span className="px-2 py-1">
              {paginaActual + 1} / {totalPaginas}
            </span>
            <button
              type="button"
              disabled={paginaActual >= totalPaginas - 1}
              onClick={() => setPage((p) => Math.min(totalPaginas - 1, p + 1))}
              className="rounded px-2 py-1 border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800"
              aria-label="Página siguiente"
            >
              ›
            </button>
          </div>
        </div>
      )}

      {/* ── Botón completar ── */}
      {revisadas === entries.length && entries.length > 0 && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onComplete}
            className={
              "px-4 py-2 rounded-lg text-sm font-semibold text-white " +
              "bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 " +
              "transition-colors duration-150"
            }
          >
            Revisión completada
          </button>
        </div>
      )}
    </div>
  )
}

export default ReviewPanel
