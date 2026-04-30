/**
 * Panel de validación de marcas nuevas antes de escribirlas
 * en la batería local (brand_cache.json).
 *
 * Solo aparece cuando el job está en PENDIENTE_VALIDACION_MARCAS.
 * Permite al usuario aceptar, rechazar o editar inline el nombre de
 * cada marca nueva antes de confirmar la selección.
 *
 * @author Carlitos6712
 * @param jobId      - Identificador del job en validación.
 * @param onComplete - Callback llamado tras confirmar la selección.
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  type BrandPendingEntry,
  type BrandValidationAction,
  type BrandValidationResult,
  validateBrands,
} from '../api/client'

// ─── Tipos locales ────────────────────────────────────────────────────────────

type BrandDecision = 'accept' | 'reject'

interface RowState {
  decision: BrandDecision
  editedName: string
  isEditing: boolean
}

interface BrandValidationPanelProps {
  jobId: string
  /** Marcas pendientes ya cargadas por el padre (desde el WebSocket payload o por fetch). */
  pendingBrands: BrandPendingEntry[]
  onComplete: (result: BrandValidationResult) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function confidenceBadge(confidence: 'high' | 'medium' | 'low'): React.ReactElement {
  const map: Record<string, string> = {
    high: 'bg-green-100 text-green-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-red-100 text-red-800',
  }
  const label: Record<string, string> = {
    high: 'Alta',
    medium: 'Media',
    low: 'Baja',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${map[confidence]}`}>
      {label[confidence]}
    </span>
  )
}

// ─── Componente ───────────────────────────────────────────────────────────────

const BrandValidationPanel: React.FC<BrandValidationPanelProps> = ({
  jobId,
  pendingBrands,
  onComplete,
}) => {
  const [rows, setRows] = useState<RowState[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<BrandValidationResult | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Inicializar rows cuando llegan pendingBrands
  useEffect(() => {
    setRows(
      pendingBrands.map((b) => ({
        decision: 'accept' as BrandDecision,
        editedName: b.brand_name,
        isEditing: false,
      })),
    )
    setSubmitResult(null)
    setSubmitError(null)
  }, [pendingBrands])

  const toggleDecision = useCallback((idx: number) => {
    setRows((prev) =>
      prev.map((r, i) =>
        i === idx
          ? { ...r, decision: r.decision === 'accept' ? 'reject' : 'accept' }
          : r,
      ),
    )
  }, [])

  const handleNameBlur = useCallback((idx: number, value: string) => {
    setRows((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, editedName: value, isEditing: false } : r)),
    )
  }, [])

  const acceptAll = useCallback(() => {
    setRows((prev) => prev.map((r) => ({ ...r, decision: 'accept' as BrandDecision })))
  }, [])

  const rejectAll = useCallback(() => {
    setRows((prev) => prev.map((r) => ({ ...r, decision: 'reject' as BrandDecision })))
  }, [])

  const handleConfirm = useCallback(async () => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const items = pendingBrands.map((brand, idx) => {
        const row = rows[idx]
        const nameChanged = row.editedName.trim() !== brand.brand_name.trim()
        let action: BrandValidationAction

        if (row.decision === 'reject') {
          action = 'reject'
        } else if (nameChanged) {
          action = 'edit'
        } else {
          action = 'accept'
        }

        return {
          ean: brand.ean,
          brand_name: brand.brand_name,
          action,
          ...(action === 'edit' ? { edited_name: row.editedName.trim() } : {}),
        }
      })

      const result = await validateBrands(jobId, { items })
      setSubmitResult(result)
      onComplete(result)
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message: string }).message)
          : 'Error al confirmar la validación.'
      setSubmitError(message)
    } finally {
      setSubmitting(false)
    }
  }, [jobId, pendingBrands, rows, onComplete])

  // ── Estado vacío ─────────────────────────────────────────────────────────────
  if (pendingBrands.length === 0) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center">
        <p className="text-sm text-amber-700">No se encontraron marcas nuevas en este job.</p>
      </div>
    )
  }

  const acceptedCount = rows.filter((r) => r.decision === 'accept').length
  const rejectedCount = rows.filter((r) => r.decision === 'reject').length
  const total = pendingBrands.length

  // ── Resultado post-confirmación ───────────────────────────────────────────────
  if (submitResult) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-6 text-center">
        <p className="text-sm font-medium text-green-800">
          ✓ {submitResult.accepted} marcas guardadas en batería ·{' '}
          {submitResult.edited} editadas · {submitResult.rejected} rechazadas
        </p>
      </div>
    )
  }

  // ── Panel principal ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Barra superior */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-600">
          <span className="font-medium text-green-700">{acceptedCount} aceptadas</span>
          {' · '}
          <span className="font-medium text-red-700">{rejectedCount} rechazadas</span>
          {' · '}
          <span className="text-gray-500">{total} totales</span>
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={acceptAll}
            className="rounded-md border border-green-300 bg-white px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 focus:outline-none focus:ring-2 focus:ring-green-500"
          >
            Aceptar todas
          </button>
          <button
            type="button"
            onClick={rejectAll}
            className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            Rechazar todas
          </button>
        </div>
      </div>

      {/* Tabla */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-500">EAN</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Marca</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Fuente</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Confianza</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Decisión</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {pendingBrands.map((brand, idx) => {
              const row = rows[idx] ?? { decision: 'accept', editedName: brand.brand_name, isEditing: false }
              const isRejected = row.decision === 'reject'
              return (
                <tr key={brand.ean} className={isRejected ? 'opacity-50' : ''}>
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-gray-600">
                    {brand.ean}
                  </td>
                  <td className="px-4 py-2">
                    {/* Edición inline: click para editar, blur para confirmar */}
                    <input
                      type="text"
                      value={row.editedName}
                      disabled={isRejected}
                      onChange={(e) =>
                        setRows((prev) =>
                          prev.map((r, i) =>
                            i === idx ? { ...r, editedName: e.target.value } : r,
                          ),
                        )
                      }
                      onBlur={(e) => handleNameBlur(idx, e.target.value)}
                      className={`w-full rounded border px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-amber-500 ${
                        isRejected
                          ? 'cursor-not-allowed border-gray-200 bg-gray-50 text-gray-400'
                          : 'border-gray-300 bg-white text-gray-900'
                      }`}
                    />
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">
                    {brand.source}
                  </td>
                  <td className="px-4 py-2">{confidenceBadge(brand.confidence)}</td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      onClick={() => toggleDecision(idx)}
                      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                        isRejected
                          ? 'bg-red-100 text-red-700 hover:bg-red-200'
                          : 'bg-green-100 text-green-700 hover:bg-green-200'
                      }`}
                    >
                      {isRejected ? '✗ Rechazar' : '✓ Aceptar'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Error */}
      {submitError && (
        <p className="text-sm text-red-600">{submitError}</p>
      )}

      {/* Botón confirmar */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={submitting}
          className="inline-flex items-center gap-2 rounded-md bg-amber-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting && (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          )}
          {submitting ? 'Confirmando…' : 'Confirmar selección'}
        </button>
      </div>
    </div>
  )
}

export default BrandValidationPanel
