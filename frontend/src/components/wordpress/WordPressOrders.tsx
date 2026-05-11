/**
 * Panel de pedidos WooCommerce.
 * Lista pedidos y permite cambiar su estado.
 *
 * @author Carlos Vico
 */
import { useEffect, useState } from 'react'
import { listWordPressOrders, updateWordPressOrderStatus } from '@/api/client'
import type { WooOrder, WooOrderStatus } from '@/types/wordpress'

const STATUS_COLORS: Record<WooOrderStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  'on-hold': 'bg-orange-100 text-orange-800',
  completed: 'bg-green-100 text-green-800',
  cancelled: 'bg-gray-100 text-gray-700',
  refunded: 'bg-purple-100 text-purple-800',
  failed: 'bg-red-100 text-red-800',
  trash: 'bg-gray-100 text-gray-500',
}

const VALID_STATUSES: WooOrderStatus[] = [
  'pending', 'processing', 'on-hold', 'completed', 'cancelled', 'refunded',
]

export default function WordPressOrders() {
  const [orders, setOrders] = useState<WooOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [statusFilter, setStatusFilter] = useState('any')
  const [selectedOrder, setSelectedOrder] = useState<WooOrder | null>(null)
  const [newStatus, setNewStatus] = useState<WooOrderStatus>('processing')
  const [updating, setUpdating] = useState(false)
  const limit = 50

  const load = async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const items = await listWordPressOrders(limit, newOffset, statusFilter)
      setOrders(items)
      setOffset(newOffset)
      setHasMore(items.length === limit)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando pedidos.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [statusFilter])

  const handleUpdateStatus = async () => {
    if (!selectedOrder) return
    setUpdating(true)
    try {
      const updated = await updateWordPressOrderStatus(selectedOrder.id, newStatus)
      setOrders((prev) => prev.map((o) => (o.id === updated.id ? updated : o)))
      setSelectedOrder(null)
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error actualizando estado.')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setOffset(0) }}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        >
          <option value="any">Todos</option>
          {VALID_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button onClick={() => load(offset)} disabled={loading} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">
          ↻ Refrescar
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['Nº Pedido', 'Cliente', 'Total', 'Estado', 'Fecha', 'Acciones'].map((h) => (
                <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={6} className="px-6 py-8 text-center text-gray-500">Cargando pedidos...</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan={6} className="px-6 py-8 text-center text-gray-500">Sin pedidos.</td></tr>
            ) : orders.map((o) => (
              <tr key={o.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">#{o.number}</td>
                <td className="px-6 py-4 text-sm text-gray-700">
                  {o.billing.first_name} {o.billing.last_name}
                  <div className="text-xs text-gray-400">{o.billing.email}</div>
                </td>
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{o.total} {o.currency}</td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs font-medium rounded ${STATUS_COLORS[o.status]}`}>
                    {o.status}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {new Date(o.date_created).toLocaleDateString('es-ES')}
                </td>
                <td className="px-6 py-4 text-sm">
                  <button
                    onClick={() => { setSelectedOrder(o); setNewStatus(o.status) }}
                    className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                  >
                    Cambiar estado
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-end gap-2">
        <button onClick={() => load(Math.max(0, offset - limit))} disabled={offset === 0 || loading} className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 text-sm">Anterior</button>
        <button onClick={() => load(offset + limit)} disabled={!hasMore || loading} className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 text-sm">Siguiente</button>
      </div>

      {selectedOrder && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg max-w-sm w-full p-6 space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Cambiar estado — #{selectedOrder.number}</h3>
            <select
              value={newStatus}
              onChange={(e) => setNewStatus(e.target.value as WooOrderStatus)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              {VALID_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <div className="flex gap-3">
              <button onClick={() => setSelectedOrder(null)} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">Cancelar</button>
              <button onClick={handleUpdateStatus} disabled={updating} className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium">{updating ? 'Guardando...' : 'Confirmar'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
