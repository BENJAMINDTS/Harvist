/**
 * Panel de revisión manual de traducciones generadas por IA (Fase 7.2).
 *
 * Permite aprobar, rechazar o editar descripcion_corta y descripcion_larga
 * de cada traducción de producto antes de exportar el CSV del idioma.
 * Incluye edición inline, paginación y exportación de aprobadas.
 *
 * @author BenjaminDTS
 * @param jobId  - Identificador del job.
 * @param lang   - Código ISO 639-1 del idioma (ej: 'en', 'fr').
 * @param label  - Etiqueta legible del idioma (ej: 'Inglés').
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { apiClient } from '@/api/client'

// ─── Interfaces ───────────────────────────────────────────────────────────────

interface TranslationEntry {
  codigo: string
  nombre: string
  lang: string
  descripcion_corta: string
  descripcion_larga: string
  keywords: string
  meta_description: string
  status: 'pending' | 'approved' | 'rejected'
  edited_corta: string | null
  edited_larga: string | null
}

interface ApiTranslationResponse {
  success: boolean
  data: {
    items: TranslationEntry[]
    total: number
    limit: number
    offset: number
    lang: string
  }
}

interface ApiPatchResponse {
  success: boolean
  data: {
    codigo: string
    lang: string
    status: 'pending' | 'approved' | 'rejected'
    edited_corta: string | null
    edited_larga: string | null
  }
}

interface TranslationReviewPanelProps {
  jobId: string
  lang: string
  label: string
}

// ─── Constantes ───────────────────────────────────────────────────────────────

const PAGE_SIZE = 10

type TabFilter = 'all' | 'pending' | 'approved' | 'rejected'

const STATUS_CONFIG: Record<TranslationEntry['status'], { label: string; classes: string }> = {
  pending: { label: 'Pendiente', classes: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' },
  approved: { label: 'Aprobada', classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' },
  rejected: { label: 'Rechazada', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400' },
}

// ─── Componente ───────────────────────────────────────────────────────────────

export function TranslationReviewPanel({ jobId, lang, label }: TranslationReviewPanelProps) {
  const [entries, setEntries] = useState<TranslationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabFilter>('all')
  const [page, setPage] = useState(0)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  // Estado edición corta
  const [editingCortaCodigo, setEditingCortaCodigo] = useState<string | null>(null)
  const [editingCortaText, setEditingCortaText] = useState('')
  const textareaCortaRef = useRef<HTMLTextAreaElement>(null)
  const confirmingCortaRef = useRef(false)

  // Estado edición larga
  const [editingLargaCodigo, setEditingLargaCodigo] = useState<string | null>(null)
  const [editingLargeText, setEditingLargeText] = useState('')
  const textareaLargeRef = useRef<HTMLTextAreaElement>(null)
  const confirmingLargeRef = useRef(false)

  // ── Carga de datos ───────────────────────────────────────────────────────────

  const cargarEntradas = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const allItems: TranslationEntry[] = []
      let offset = 0
      const limit = 100
      let hasMore = true
      while (hasMore) {
        const response = await apiClient.get<ApiTranslationResponse>(
          `/jobs/${jobId}/translations/${lang}/review`,
          { params: { limit, offset } }
        )
        const { items, total } = response.data.data
        allItems.push(...items)
        offset += items.length
        hasMore = allItems.length < total && items.length > 0
      }
      setEntries(allItems)
    } catch {
      setLoadError('No se pudieron cargar las traducciones.')
    } finally {
      setLoading(false)
    }
  }, [jobId, lang])

  useEffect(() => {
    cargarEntradas()
  }, [cargarEntradas])

  useEffect(() => {
    if (editingCortaCodigo && textareaCortaRef.current) textareaCortaRef.current.focus()
  }, [editingCortaCodigo])

  useEffect(() => {
    if (editingLargaCodigo && textareaLargeRef.current) textareaLargeRef.current.focus()
  }, [editingLargaCodigo])

  // ── Acción de revisión ───────────────────────────────────────────────────────

  const aplicarAccion = useCallback(
    async (
      codigo: string,
      action: 'approve' | 'reject' | 'edit',
      editedCorta?: string,
      editedLarga?: string
    ): Promise<void> => {
      setActionLoading(codigo)
      setActionError(null)
      try {
        const body: { action: string; edited_corta?: string; edited_larga?: string } = { action }
        if (action === 'edit') {
          if (editedCorta !== undefined) body.edited_corta = editedCorta
          if (editedLarga !== undefined) body.edited_larga = editedLarga
        }

        const response = await apiClient.patch<ApiPatchResponse>(
          `/jobs/${jobId}/translations/${lang}/${encodeURIComponent(codigo)}`,
          body
        )
        const { status: newStatus, edited_corta: newCorta, edited_larga: newLarga } = response.data.data

        setEntries((prev) =>
          prev.map((e) =>
            e.codigo === codigo
              ? {
                  ...e,
                  status: newStatus,
                  edited_corta: newCorta,
                  edited_larga: newLarga,
                  descripcion_corta: action === 'edit' && newCorta ? newCorta : e.descripcion_corta,
                  descripcion_larga: action === 'edit' && newLarga ? newLarga : e.descripcion_larga,
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
    [jobId, lang]
  )

  // ── Handlers edición corta ───────────────────────────────────────────────────

  const handleStartEditCorta = useCallback((entry: TranslationEntry) => {
    setEditingCortaCodigo(entry.codigo)
    setEditingCortaText(entry.edited_corta ?? entry.descripcion_corta)
  }, [])

  const handleConfirmEditCorta = useCallback(
    async (codigo: string) => {
      if (confirmingCortaRef.current) return
      confirmingCortaRef.current = true
      try {
        if (editingCortaText.trim()) {
          await aplicarAccion(codigo, 'edit', editingCortaText.trim(), undefined)
        }
        setEditingCortaCodigo(null)
        setEditingCortaText('')
      } finally {
        confirmingCortaRef.current = false
      }
    },
    [aplicarAccion, editingCortaText]
  )

  const handleCancelEditCorta = useCallback(() => {
    setEditingCortaCodigo(null)
    setEditingCortaText('')
  }, [])

  const handleKeyDownCorta = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>, codigo: string) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleConfirmEditCorta(codigo) }
      else if (e.key === 'Escape') handleCancelEditCorta()
    },
    [handleConfirmEditCorta, handleCancelEditCorta]
  )

  // ── Handlers edición larga ───────────────────────────────────────────────────

  const handleStartEditLarga = useCallback((entry: TranslationEntry) => {
    setEditingLargaCodigo(entry.codigo)
    setEditingLargeText(entry.edited_larga ?? entry.descripcion_larga)
  }, [])

  const handleConfirmEditLarga = useCallback(
    async (codigo: string) => {
      if (confirmingLargeRef.current) return
      confirmingLargeRef.current = true
      try {
        if (editingLargeText.trim()) {
          await aplicarAccion(codigo, 'edit', undefined, editingLargeText.trim())
        }
        setEditingLargaCodigo(null)
        setEditingLargeText('')
      } finally {
        confirmingLargeRef.current = false
      }
    },
    [aplicarAccion, editingLargeText]
  )

  const handleCancelEditLarga = useCallback(() => {
    setEditingLargaCodigo(null)
    setEditingLargeText('')
  }, [])

  const handleKeyDownLarga = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>, codigo: string) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleConfirmEditLarga(codigo) }
      else if (e.key === 'Escape') handleCancelEditLarga()
    },
    [handleConfirmEditLarga, handleCancelEditLarga]
  )

  // ── Aprobación masiva ────────────────────────────────────────────────────────

  const handleAprobarTodas = useCallback(async () => {
    const pendientes = entries.filter((e) => e.status === 'pending')
    for (const entry of pendientes) {
      await aplicarAccion(entry.codigo, 'approve')
    }
  }, [entries, aplicarAccion])

  // ── Exportar aprobadas ───────────────────────────────────────────────────────

  const handleExportar = useCallback(async () => {
    setExportLoading(true)
    setExportError(null)
    try {
      const response = await apiClient.get<Blob>(
        `/files/${jobId}/translations/${lang}`,
        { params: { only_approved: true }, responseType: 'blob' }
      )
      if (response.status === 204) {
        setExportError('No hay traducciones aprobadas para exportar.')
        return
      }
      const url = URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `traducciones_${lang}_aprobadas_${jobId.slice(0, 8)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setExportError('Error al descargar el CSV de aprobadas.')
    } finally {
      setExportLoading(false)
    }
  }, [jobId, lang])

  // ── Filtrado y paginación ────────────────────────────────────────────────────

  const filtradas = entries.filter((e) => activeTab === 'all' || e.status === activeTab)
  const totalPaginas = Math.max(1, Math.ceil(filtradas.length / PAGE_SIZE))
  const paginaActual = Math.min(page, totalPaginas - 1)
  const entradasPagina = filtradas.slice(paginaActual * PAGE_SIZE, (paginaActual + 1) * PAGE_SIZE)

  const counts = {
    all: entries.length,
    pending: entries.filter((e) => e.status === 'pending').length,
    approved: entries.filter((e) => e.status === 'approved').length,
    rejected: entries.filter((e) => e.status === 'rejected').length,
  }

  const revisadas = counts.approved + counts.rejected

  // ── Render ───────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 gap-2 text-sm text-gray-500">
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        Cargando traducciones {label}…
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400">
        {loadError}
        <button
          type="button"
          onClick={cargarEntradas}
          className="ml-2 underline hover:no-underline"
        >
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* ── Cabecera ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-gray-600 dark:text-gray-400">
          <span className="font-semibold text-gray-800 dark:text-gray-200">{revisadas}</span>
          {' / '}
          <span className="font-semibold">{counts.all}</span>
          {' revisadas'}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleAprobarTodas}
            disabled={counts.pending === 0 || actionLoading !== null}
            className="rounded-lg border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Aprobar todas ({counts.pending})
          </button>
          <button
            type="button"
            onClick={handleExportar}
            disabled={exportLoading || counts.approved === 0}
            className="flex items-center gap-1.5 rounded-lg border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 px-3 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {exportLoading ? (
              <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
        <p className="text-xs text-red-600 dark:text-red-400">{exportError}</p>
      )}
      {actionError && (
        <p className="text-xs text-red-600 dark:text-red-400">{actionError}</p>
      )}

      {/* ── Tabs ── */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {(['all', 'pending', 'approved', 'rejected'] as TabFilter[]).map((tab) => {
          const tabLabels: Record<TabFilter, string> = {
            all: `Todas${counts.all ? ` ${counts.all}` : ''}`,
            pending: `Pendientes${counts.pending ? ` ${counts.pending}` : ''}`,
            approved: `Aprobadas${counts.approved ? ` ${counts.approved}` : ''}`,
            rejected: `Rechazadas${counts.rejected ? ` ${counts.rejected}` : ''}`,
          }
          return (
            <button
              key={tab}
              type="button"
              onClick={() => { setActiveTab(tab); setPage(0) }}
              className={
                'px-3 py-1.5 text-xs font-medium rounded-t border-b-2 transition-colors ' +
                (activeTab === tab
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200')
              }
            >
              {tabLabels[tab]}
            </button>
          )
        })}
      </div>

      {/* ── Tabla ── */}
      {entradasPagina.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-500">
          No hay traducciones en esta categoría.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 text-left w-24">Código</th>
                <th className="px-3 py-2 text-left w-32">Nombre</th>
                <th className="px-3 py-2 text-left">Corta</th>
                <th className="px-3 py-2 text-left">Larga</th>
                <th className="px-3 py-2 text-left w-24">Estado</th>
                <th className="px-3 py-2 text-right w-28">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-900">
              {entradasPagina.map((entry) => {
                const isEditingCorta = editingCortaCodigo === entry.codigo
                const isEditingLarga = editingLargaCodigo === entry.codigo
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
                    <td className="px-3 py-2 text-gray-800 dark:text-gray-200 align-top text-xs">
                      {entry.nombre}
                    </td>

                    {/* ── Descripción corta ── */}
                    <td
                      className="px-3 py-2 align-top cursor-pointer"
                      onClick={() => !isEditingCorta && handleStartEditCorta(entry)}
                      title="Click para editar descripción corta"
                    >
                      {isEditingCorta ? (
                        <textarea
                          ref={textareaCortaRef}
                          value={editingCortaText}
                          onChange={(e) => setEditingCortaText(e.target.value)}
                          onBlur={() => handleConfirmEditCorta(entry.codigo)}
                          onKeyDown={(e) => handleKeyDownCorta(e, entry.codigo)}
                          rows={3}
                          className={
                            'w-full rounded border border-blue-400 dark:border-blue-500 bg-white dark:bg-gray-800 ' +
                            'px-2 py-1 text-sm text-gray-800 dark:text-gray-100 ' +
                            'focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none'
                          }
                          aria-label={`Editar descripción corta ${lang} de ${entry.codigo}`}
                        />
                      ) : (
                        <span className="text-gray-700 dark:text-gray-300 line-clamp-2 hover:line-clamp-none text-xs">
                          {entry.edited_corta ?? entry.descripcion_corta}
                        </span>
                      )}
                    </td>

                    {/* ── Descripción larga ── */}
                    <td
                      className="px-3 py-2 align-top cursor-pointer"
                      onClick={() => !isEditingLarga && handleStartEditLarga(entry)}
                      title="Click para editar descripción larga"
                    >
                      {isEditingLarga ? (
                        <textarea
                          ref={textareaLargeRef}
                          value={editingLargeText}
                          onChange={(e) => setEditingLargeText(e.target.value)}
                          onBlur={() => handleConfirmEditLarga(entry.codigo)}
                          onKeyDown={(e) => handleKeyDownLarga(e, entry.codigo)}
                          rows={6}
                          className={
                            'w-full rounded border border-blue-400 dark:border-blue-500 bg-white dark:bg-gray-800 ' +
                            'px-2 py-1 text-xs text-gray-800 dark:text-gray-100 ' +
                            'focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y'
                          }
                          aria-label={`Editar descripción larga ${lang} de ${entry.codigo}`}
                        />
                      ) : (
                        <span className="text-gray-600 dark:text-gray-400 line-clamp-3 hover:line-clamp-none text-xs">
                          {entry.edited_larga ?? entry.descripcion_larga}
                        </span>
                      )}
                    </td>

                    {/* ── Estado ── */}
                    <td className="px-3 py-2 align-top">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${statusCfg.classes}`}>
                        {statusCfg.label}
                      </span>
                    </td>

                    {/* ── Acciones ── */}
                    <td className="px-3 py-2 align-top text-right">
                      <div className="flex items-center justify-end gap-1">
                        {/* Aprobar */}
                        <button
                          type="button"
                          onClick={() => aplicarAccion(entry.codigo, 'approve')}
                          disabled={entry.status === 'approved' || isLoading}
                          aria-label={`Aprobar traducción ${lang} de ${entry.codigo}`}
                          title="Aprobar"
                          className={
                            'rounded p-1 transition-colors duration-150 ' +
                            (entry.status === 'approved' || isLoading
                              ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                              : 'text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20')
                          }
                        >
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        </button>

                        {/* Rechazar */}
                        <button
                          type="button"
                          onClick={() => aplicarAccion(entry.codigo, 'reject')}
                          disabled={entry.status === 'rejected' || isLoading}
                          aria-label={`Rechazar traducción ${lang} de ${entry.codigo}`}
                          title="Rechazar"
                          className={
                            'rounded p-1 transition-colors duration-150 ' +
                            (entry.status === 'rejected' || isLoading
                              ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                              : 'text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20')
                          }
                        >
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                          </svg>
                        </button>

                        {/* Loading spinner */}
                        {isLoading && (
                          <svg className="animate-spin h-4 w-4 text-blue-500" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                          </svg>
                        )}
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
            Página {paginaActual + 1} de {totalPaginas}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={paginaActual === 0}
              className="rounded px-2 py-1 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ‹
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPaginas - 1, p + 1))}
              disabled={paginaActual >= totalPaginas - 1}
              className="rounded px-2 py-1 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ›
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
