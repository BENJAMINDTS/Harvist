/**
 * Panel de inventario/stock de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooStock, updateOdooStockQuant, deleteOdooStockQuant } from '@/api/client'
import type { OdooStockLine } from '@/types/odoo'

const formatField = (v: [number, string] | false | undefined) => (v ? v[1] : '—')
const formatDate = (v: string | false | undefined) =>
  v ? new Date(v).toLocaleDateString('es-ES') : '—'

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'
const SECTION_CLS = 'border border-gray-100 rounded-lg p-4 space-y-3'
const SECTION_TITLE_CLS = 'text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3'
const RO_CLS = `${INPUT_CLS} bg-gray-50 text-gray-500`

export default function OdooInventory() {
  const [items, setItems] = useState<OdooStockLine[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingQuant, setEditingQuant] = useState<OdooStockLine | null>(null)
  const [pagination, setPagination] = useState({ limit: 50, offset: 0, total: 0, has_more: false })

  const load = async (limit = 50, offset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listOdooStock(limit, offset)
      setItems(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando stock')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este registro de stock? Solo es posible si la cantidad es 0 o con permisos de administrador.')) return
    try {
      await deleteOdooStockQuant(id)
      load(pagination.limit, pagination.offset)
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando quant')
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Producto</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Ubicación</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Cantidad</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Reservada</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Disponible</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Lote</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Cargando stock...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Sin stock</td></tr>
            ) : items.map((s) => (
              <tr key={s.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{formatField(s.product_id)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(s.location_id)}</td>
                <td className="px-6 py-4 text-sm text-gray-900">{s.quantity.toFixed(2)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{s.reserved_quantity.toFixed(2)}</td>
                <td className="px-6 py-4 text-sm font-medium text-gray-900">
                  {(s.quantity - s.reserved_quantity).toFixed(2)}
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(s.lot_id)}</td>
                <td className="px-6 py-4 text-sm">
                  <div className="flex gap-3">
                    <button
                      onClick={() => setEditingQuant(s)}
                      className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(s.id)}
                      className="text-red-600 hover:text-red-800 text-xs font-medium"
                    >
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination.total > 0 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>
            {pagination.offset + 1} –{' '}
            {Math.min(pagination.offset + pagination.limit, pagination.total)} de{' '}
            {pagination.total}
          </div>
          <div className="flex gap-2">
            <button
              disabled={pagination.offset === 0}
              onClick={() => load(pagination.limit, Math.max(0, pagination.offset - pagination.limit))}
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              disabled={!pagination.has_more}
              onClick={() => load(pagination.limit, pagination.offset + pagination.limit)}
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}

      {editingQuant && (
        <EditQuantModal
          quant={editingQuant}
          onClose={() => setEditingQuant(null)}
          onSuccess={() => {
            setEditingQuant(null)
            load(pagination.limit, pagination.offset)
          }}
        />
      )}
    </div>
  )
}

// ── Edit modal ────────────────────────────────────────────────────────────

interface EditQuantModalProps {
  quant: OdooStockLine
  onClose: () => void
  onSuccess: () => void
}

function EditQuantModal({ quant, onClose, onSuccess }: EditQuantModalProps) {
  const [inventoryQty, setInventoryQty] = useState(
    String(quant.inventory_quantity ?? quant.quantity),
  )
  const [inventoryDate, setInventoryDate] = useState(
    quant.inventory_date ? quant.inventory_date.slice(0, 10) : '',
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    const qty = parseFloat(inventoryQty)
    if (isNaN(qty) || qty < 0) {
      setError('Cantidad inventariada debe ser ≥ 0.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const payload: Partial<OdooStockLine> = { inventory_quantity: qty }
      if (inventoryDate) payload.inventory_date = inventoryDate
      await updateOdooStockQuant(quant.id, payload)
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error actualizando quant')
    } finally {
      setSubmitting(false)
    }
  }

  const diffQty = parseFloat(inventoryQty) - quant.quantity
  const diffColor = diffQty > 0 ? 'text-green-600' : diffQty < 0 ? 'text-red-600' : 'text-gray-500'

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <h3 className="text-lg font-semibold text-gray-900">Editar quant de stock</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">

          {/* Información de solo lectura */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Información del registro</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Producto</label>
                <input type="text" value={formatField(quant.product_id)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Ubicación</label>
                <input type="text" value={formatField(quant.location_id)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Cantidad real</label>
                <input type="text" value={quant.quantity.toFixed(4)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Cantidad reservada</label>
                <input type="text" value={quant.reserved_quantity.toFixed(4)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Lote / Nº serie</label>
                <input type="text" value={formatField(quant.lot_id)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Paquete</label>
                <input type="text" value={formatField(quant.package_id)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Propietario</label>
                <input type="text" value={formatField(quant.owner_id)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Responsable</label>
                <input type="text" value={formatField(quant.user_id)} disabled className={RO_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Fecha entrada</label>
                <input type="text" value={formatDate(quant.in_date)} disabled className={RO_CLS} />
              </div>
            </div>
          </div>

          {/* Ajuste de inventario */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Ajuste de inventario</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>
                  Nueva cantidad inventariada <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="0.0001"
                  min="0"
                  value={inventoryQty}
                  onChange={(e) => setInventoryQty(e.target.value)}
                  className={INPUT_CLS}
                  autoFocus
                />
              </div>
              <div>
                <label className={LABEL_CLS}>Diferencia respecto al real</label>
                <input
                  type="text"
                  value={isNaN(diffQty) ? '—' : `${diffQty >= 0 ? '+' : ''}${diffQty.toFixed(4)}`}
                  disabled
                  className={`${RO_CLS} font-medium ${diffColor}`}
                />
              </div>
              <div>
                <label className={LABEL_CLS}>Fecha inventario programada</label>
                <input
                  type="date"
                  value={inventoryDate}
                  onChange={(e) => setInventoryDate(e.target.value)}
                  className={INPUT_CLS}
                />
              </div>
            </div>
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mt-2">
              Al guardar se aplicará el ajuste en Odoo y se creará un movimiento de stock si la cantidad difiere.
            </p>
          </div>

        </div>

        <div className="px-6 py-4 border-t border-gray-200 space-y-3 flex-shrink-0">
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Aplicando...' : 'Guardar y aplicar ajuste'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
