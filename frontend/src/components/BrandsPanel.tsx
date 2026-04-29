/**
 * Panel de visualización de marcas resueltas para un job completado.
 *
 * Permite filtrar por fuente y nivel de confianza, y descargar el CSV.
 *
 * @author BenjaminDTS
 * @param jobId - Identificador del job del que mostrar las marcas.
 * @param brandsData - Array de marcas resueltas recibido del endpoint.
 */
import React, { useMemo, useState } from 'react'
import type { BrandEntry, BrandSource } from '@/api/client'
import { downloadBrandsCsv } from '@/api/client'

// ---------------------------------------------------------------------------
// Tipos y constantes
// ---------------------------------------------------------------------------

interface BrandsPanelProps {
  jobId: string
  brandsData: BrandEntry[]
}

const ITEMS_PER_PAGE = 50

const SOURCE_LABELS: Record<BrandSource, string> = {
  amazon: 'Amazon',
  cache_gs1: 'GS1 Local',
  open_data_api: 'Open Data',
  google_dorking: 'Google',
  bing_search: 'Bing',
  not_found: 'No encontrado',
  ean_invalido: 'EAN inválido',
}

const CONFIDENCE_CONFIG: Record<
  'high' | 'medium' | 'low',
  { label: string; classes: string }
> = {
  high: {
    label: 'Alta',
    classes: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  },
  medium: {
    label: 'Media',
    classes: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300',
  },
  low: {
    label: 'Baja',
    classes: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  },
}

const ALL_SOURCES: BrandSource[] = [
  'amazon',
  'cache_gs1',
  'open_data_api',
  'google_dorking',
  'bing_search',
  'not_found',
  'ean_invalido',
]

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

interface ConfidenceBadgeProps {
  confidence: 'high' | 'medium' | 'low'
}

const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ confidence }) => {
  const { label, classes } = CONFIDENCE_CONFIG[confidence]
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}>
      {label}
    </span>
  )
}

interface SourceBadgeProps {
  source: BrandSource
}

const SourceBadge: React.FC<SourceBadgeProps> = ({ source }) => (
  <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
    {SOURCE_LABELS[source]}
  </span>
)

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

/**
 * Panel de visualización de marcas resueltas para un job completado.
 * Permite filtrar por fuente y nivel de confianza, y descargar el CSV.
 *
 * @author BenjaminDTS
 */
export const BrandsPanel: React.FC<BrandsPanelProps> = ({ jobId, brandsData }) => {
  const [selectedSources, setSelectedSources] = useState<Set<BrandSource>>(new Set())
  const [selectedConfidence, setSelectedConfidence] = useState<'all' | 'high' | 'medium' | 'low'>('all')
  const [page, setPage] = useState(1)
  const [downloading, setDownloading] = useState(false)

  // ── Counters ────────────────────────────────────────────────────────────
  const brandsResolved = useMemo(
    () => brandsData.filter((b) => b.source !== 'not_found' && b.source !== 'ean_invalido').length,
    [brandsData],
  )
  const brandsNotFound = brandsData.length - brandsResolved

  // ── Filtering ───────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return brandsData.filter((b) => {
      const sourceMatch = selectedSources.size === 0 || selectedSources.has(b.source)
      const confMatch = selectedConfidence === 'all' || b.confidence === selectedConfidence
      return sourceMatch && confMatch
    })
  }, [brandsData, selectedSources, selectedConfidence])

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE))
  const paginated = filtered.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE)

  const handleSourceToggle = (source: BrandSource): void => {
    setSelectedSources((prev) => {
      const next = new Set(prev)
      if (next.has(source)) {
        next.delete(source)
      } else {
        next.add(source)
      }
      return next
    })
    setPage(1)
  }

  const handleConfidenceChange = (value: 'all' | 'high' | 'medium' | 'low'): void => {
    setSelectedConfidence(value)
    setPage(1)
  }

  const handleDownload = async (): Promise<void> => {
    if (brandsResolved === 0) return
    setDownloading(true)
    try {
      const blob = await downloadBrandsCsv(jobId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `marcas_${jobId}.csv`
      anchor.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Contador resumen */}
      <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
        <span>
          <strong className="text-gray-800 dark:text-gray-200">{brandsData.length}</strong> marcas
        </span>
        <span className="text-green-600 dark:text-green-400">
          <strong>{brandsResolved}</strong> resueltas
        </span>
        <span className="text-red-500 dark:text-red-400">
          <strong>{brandsNotFound}</strong> sin resolver
        </span>
      </div>

      {/* Filtros */}
      <div className="space-y-3">
        {/* Filtro por fuente */}
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
            Fuente
          </p>
          <div className="flex flex-wrap gap-1.5">
            {ALL_SOURCES.map((source) => {
              const active = selectedSources.has(source)
              return (
                <button
                  key={source}
                  type="button"
                  onClick={() => handleSourceToggle(source)}
                  className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400 ${
                    active
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                  aria-pressed={active}
                >
                  {SOURCE_LABELS[source]}
                </button>
              )
            })}
            {selectedSources.size > 0 && (
              <button
                type="button"
                onClick={() => { setSelectedSources(new Set()); setPage(1) }}
                className="px-2.5 py-1 rounded text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 focus:outline-none"
              >
                Limpiar
              </button>
            )}
          </div>
        </div>

        {/* Filtro por confianza */}
        <div className="flex items-center gap-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Confianza:
          </p>
          {(['all', 'high', 'medium', 'low'] as const).map((val) => (
            <button
              key={val}
              type="button"
              onClick={() => handleConfidenceChange(val)}
              className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400 ${
                selectedConfidence === val
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {val === 'all' ? 'Todos' : CONFIDENCE_CONFIG[val].label}
            </button>
          ))}
        </div>
      </div>

      {/* Botón descarga */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void handleDownload()}
          disabled={brandsResolved === 0 || downloading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-blue-300 dark:border-blue-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm font-medium text-blue-700 dark:text-blue-400 transition-colors hover:bg-blue-50 dark:hover:bg-blue-950 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {downloading ? (
            <>
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
              </svg>
              Descargando…
            </>
          ) : (
            <>
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
              Descargar marcas.csv
            </>
          )}
        </button>
      </div>

      {/* Tabla */}
      {paginated.length === 0 ? (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
          No se encontraron marcas con los filtros seleccionados
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                {['Código', 'EAN', 'Marca', 'Fabricante', 'Fuente', 'Confianza'].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-900">
              {paginated.map((brand, idx) => (
                <tr
                  key={`${brand.codigo}-${idx}`}
                  className="hover:bg-gray-50 dark:hover:bg-gray-800/50"
                >
                  <td className="px-3 py-2 font-mono text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    {brand.codigo}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap">
                    {brand.ean || '—'}
                  </td>
                  <td className="px-3 py-2 text-gray-800 dark:text-gray-200">
                    {brand.brand_name ?? <span className="text-gray-400 dark:text-gray-600 italic">—</span>}
                  </td>
                  <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                    {brand.manufacturer ?? <span className="text-gray-400 dark:text-gray-600 italic">—</span>}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <SourceBadge source={brand.source} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <ConfidenceBadge confidence={brand.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginación */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">
            Página {page} de {totalPages} · {filtered.length} resultados
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-400"
            >
              ←
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-400"
            >
              →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
