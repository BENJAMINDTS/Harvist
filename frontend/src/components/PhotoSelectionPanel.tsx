/**
 * Panel de selección visual de fotos candidatas por producto.
 * Aparece automáticamente cuando el job está en PENDIENTE_SELECCION_FOTOS.
 * El usuario elige una foto por producto antes de generar el ZIP.
 *
 * @author BenjaminDTS
 * @param jobId      - Identificador del job en selección.
 * @param onComplete - Callback llamado tras confirmar la selección.
 */

import React, { useCallback, useEffect, useState } from 'react'
import { apiClient } from '@/api/client'

interface CandidateInfo {
  index: number
  url: string
  width: number
  height: number
  size_bytes: number
}

interface ProductPhotos {
  codigo: string
  nombre: string
  n_candidates: number
  candidates: CandidateInfo[]
  selected_index: number | null
}

interface PhotoSelectionItem {
  codigo: string
  selected_index: number
}

interface PhotoSelectionPanelProps {
  jobId: string
  onComplete: () => Promise<void>
}

/**
 * Estado interno del selector de fotos.
 */
interface SelectionState {
  [codigo: string]: number | null
}

const PhotoSelectionPanel: React.FC<PhotoSelectionPanelProps> = ({ jobId, onComplete }) => {
  const [products, setProducts] = useState<ProductPhotos[]>([])
  const [selections, setSelections] = useState<SelectionState>({})
  const [loading, setLoading] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [imageLoadErrors, setImageLoadErrors] = useState<Set<string>>(new Set())

  // Cargar productos con candidatas
  useEffect(() => {
    const fetchProducts = async (): Promise<void> => {
      try {
        setLoading(true)
        setError(null)
        const response = await apiClient.get<{
          success: boolean
          data: ProductPhotos[]
          message: string
        }>(`/jobs/${jobId}/photos`)

        const productsData = response.data.data
        setProducts(productsData)

        // Inicializar selecciones con la primera candidata de cada producto
        const initialSelections: SelectionState = {}
        productsData.forEach((product) => {
          initialSelections[product.codigo] = product.selected_index ?? 0
        })
        setSelections(initialSelections)
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Error al cargar las fotos candidatas.'
        setError(msg)
      } finally {
        setLoading(false)
      }
    }

    fetchProducts()
  }, [jobId])

  // Contar productos con selección
  const selectedCount = Object.values(selections).filter((idx) => idx !== null).length
  const totalCount = products.length

  // Marcar imagen como no cargada
  const handleImageError = useCallback((codigo: string): void => {
    setImageLoadErrors((prev) => new Set([...prev, `${codigo}-error`]))
  }, [])

  // Click en candidata — seleccionar para ese producto
  const handleSelectCandidate = useCallback((codigo: string, index: number): void => {
    setSelections((prev) => ({
      ...prev,
      [codigo]: index,
    }))
  }, [])

  // Confirmar selecciones y generar ZIP
  const handleConfirm = useCallback(async (): Promise<void> => {
    if (selectedCount !== totalCount) return

    setConfirming(true)
    setError(null)

    try {
      const items: PhotoSelectionItem[] = products.map((product) => ({
        codigo: product.codigo,
        selected_index: selections[product.codigo] ?? 0,
      }))

      await apiClient.post<{
        success: boolean
        data: { confirmadas: number; zip_listo: boolean }
        message: string
      }>(`/jobs/${jobId}/photos/confirm`, { selections: items })

      // Callback al padre
      await onComplete()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al confirmar la selección.'
      setError(msg)
    } finally {
      setConfirming(false)
    }
  }, [jobId, products, selections, selectedCount, totalCount, onComplete])

  if (loading) {
    return (
      <section
        aria-label="Cargando fotos candidatas"
        className="w-full max-w-4xl mx-auto flex flex-col gap-6 px-4 py-6 sm:px-0"
      >
        <div className="flex items-center justify-center py-12">
          <div className="flex flex-col items-center gap-4">
            <svg
              className="w-8 h-8 animate-spin text-blue-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z"
              />
            </svg>
            <span className="text-sm text-gray-600 dark:text-gray-400">
              Cargando fotos candidatas…
            </span>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section
      aria-label="Seleccionar foto por producto"
      className="w-full max-w-4xl mx-auto flex flex-col gap-6 px-4 py-6 sm:px-0"
    >
      {/* Encabezado con instrucciones */}
      <div
        className="rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 p-4"
        aria-label="Instrucciones"
      >
        <h2 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">
          Seleccionar fotos por producto
        </h2>
        <p className="text-xs text-blue-700 dark:text-blue-300">
          Se descargaron varias candidatas por producto. Haz clic en la foto que prefieras para cada uno.
          Las no seleccionadas se eliminarán.
        </p>
      </div>

      {/* Barra de progreso fija superior */}
      <div className="sticky top-0 z-10 bg-white dark:bg-gray-900 p-4 border-b border-gray-200 dark:border-gray-700 rounded-lg shadow-sm flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Progreso: {selectedCount} / {totalCount} productos con foto seleccionada
          </span>
        </div>

        {/* Barra de progreso visual */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${totalCount > 0 ? (selectedCount / totalCount) * 100 : 0}%` }}
            role="progressbar"
            aria-valuenow={selectedCount}
            aria-valuemin={0}
            aria-valuemax={totalCount}
          />
        </div>

        {/* Botón confirmar */}
        <button
          type="button"
          onClick={handleConfirm}
          disabled={selectedCount !== totalCount || confirming}
          aria-busy={confirming}
          className={
            "w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg " +
            "text-sm font-semibold text-white transition-colors duration-150 " +
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 " +
            (selectedCount === totalCount && !confirming
              ? "bg-blue-600 hover:bg-blue-700 active:bg-blue-800 cursor-pointer"
              : "bg-gray-400 dark:bg-gray-600 cursor-not-allowed opacity-60")
          }
        >
          {confirming ? (
            <>
              <svg
                className="w-4 h-4 animate-spin"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z"
                />
              </svg>
              Confirmando…
            </>
          ) : (
            'Confirmar selección'
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div
          className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 p-4"
          role="alert"
        >
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Grid de productos */}
      <div className="grid grid-cols-1 gap-6">
        {products.map((product) => {
          const selectedIdx = selections[product.codigo]
          return (
            <div
              key={product.codigo}
              className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 flex flex-col gap-3"
            >
              {/* Nombre del producto */}
              <div className="flex items-start gap-2">
                <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                  {product.codigo}
                </span>
                <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 flex-1 truncate">
                  {product.nombre}
                </span>
                <span
                  className={
                    "text-xs px-2 py-1 rounded " +
                    (selectedIdx !== null
                      ? "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400")
                  }
                >
                  {selectedIdx !== null ? 'Seleccionada' : 'Sin seleccionar'}
                </span>
              </div>

              {/* Fila horizontal de candidatas (scrollable si hay más de 5) */}
              <div className="overflow-x-auto pb-2 -mx-4 px-4">
                <div className="flex gap-3">
                  {product.candidates.map((candidate) => {
                    const isSelected = selectedIdx === candidate.index
                    const hasError = imageLoadErrors.has(`${product.codigo}-${candidate.index}`)

                    return (
                      <button
                        key={`${product.codigo}-${candidate.index}`}
                        type="button"
                        onClick={() => handleSelectCandidate(product.codigo, candidate.index)}
                        className={
                          "relative shrink-0 rounded-lg overflow-hidden transition-all duration-200 cursor-pointer " +
                          "hover:opacity-100 " +
                          (isSelected
                            ? "ring-2 ring-blue-500 scale-105"
                            : "opacity-60 hover:opacity-100")
                        }
                        aria-label={`Seleccionar candidata ${candidate.index} de ${product.nombre}`}
                      >
                        {/* Thumbnail 120x120 */}
                        <div className="w-32 h-32 bg-gray-100 dark:bg-gray-800 rounded-lg overflow-hidden flex items-center justify-center">
                          {hasError ? (
                            <div className="flex flex-col items-center justify-center w-full h-full text-gray-400 dark:text-gray-500">
                              <svg
                                className="w-6 h-6"
                                xmlns="http://www.w3.org/2000/svg"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                aria-hidden="true"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5zm10.5-11.25h.008v.008h-.008v-.008zm3 0h.008v.008h-.008v-.008z"
                                />
                              </svg>
                              <span className="text-xs mt-1">No se cargó</span>
                            </div>
                          ) : (
                            <img
                              src={candidate.url}
                              alt={`Candidata ${candidate.index} de ${product.nombre}`}
                              className="w-full h-full object-cover"
                              onError={() => handleImageError(`${product.codigo}-${candidate.index}`)}
                            />
                          )}
                        </div>

                        {/* Índice y tamaño */}
                        <div className="absolute top-2 left-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
                          #{candidate.index}
                        </div>

                        {/* Indicador de selección */}
                        {isSelected && (
                          <div className="absolute inset-0 border-2 border-blue-500 rounded-lg pointer-events-none" />
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Mensaje cuando todos están seleccionados */}
      {selectedCount === totalCount && (
        <div
          className="rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-4"
          role="status"
        >
          <p className="text-sm text-green-700 dark:text-green-300">
            Perfecto. Todos los productos tienen foto seleccionada. Presiona el botón para confirmar.
          </p>
        </div>
      )}
    </section>
  )
}

export default PhotoSelectionPanel
