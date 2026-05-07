/**
 * Módulo de gestión de pedidos de Dolibarr.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { listDolibarrOrders } from '@/api/client'
import { type DolibarrOrder, type OrderType } from '@/types/dolibarr'

export default function DolibarrOrders() {
  const [orders, setOrders] = useState<DolibarrOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [type, setType] = useState<OrderType>('customer')
  const [pagination, setPagination] = useState({
    limit: 10,
    offset: 0,
    total: 0,
    has_more: false,
  })

  const loadOrders = async (
    limit = 10,
    offset = 0,
    selectedType: OrderType = type,
  ) => {
    try {
      setLoading(true)
      const data = await listDolibarrOrders(selectedType, limit, offset)
      setOrders(data.items)
      setPagination({
        limit: data.limit,
        offset: data.offset,
        total: data.total,
        has_more: data.has_more,
      })
    } catch (err) {
      console.error('Error loading orders:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  const handleTypeChange = (newType: OrderType) => {
    setType(newType)
    loadOrders(10, 0, newType)
  }

  const getStatusLabel = (status: number): string => {
    const statusMap: Record<number, string> = {
      0: 'Borrador',
      1: 'Validado',
      2: 'Enviado',
      3: 'Entregado',
      4: 'Cancelado',
    }
    return statusMap[status] ?? `Estado ${status}`
  }

  const formatDate = (timestamp: number | string | null | undefined): string => {
    if (!timestamp) return '—'
    return new Date(Number(timestamp) * 1000).toLocaleDateString('es-ES')
  }

  const formatAmount = (value: number | string | null | undefined): string => {
    if (value === null || value === undefined) return '—'
    return `€${parseFloat(String(value)).toFixed(2)}`
  }

  return (
    <div className="space-y-6">
      {/* Toggle tipo */}
      <div className="flex gap-2">
        {(
          [
            { id: 'customer' as OrderType, label: 'Pedidos de cliente' },
            { id: 'supplier' as OrderType, label: 'Pedidos de compra' },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => handleTypeChange(t.id)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              type === t.id
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tabla */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Referencia
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Tercero ID
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Fecha
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Estado
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Total
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  Cargando...
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  Sin pedidos
                </td>
              </tr>
            ) : (
              orders.map((o) => (
                <tr key={o.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    {o.ref}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{o.socid}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {formatDate(o.date)}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span className="px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-800">
                      {getStatusLabel(o.statut)}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    {formatAmount(o.total_ttc)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Paginación */}
      {pagination.total > 0 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>
            {pagination.offset + 1} -{' '}
            {Math.min(pagination.offset + pagination.limit, pagination.total)} de{' '}
            {pagination.total}
          </div>
          <div className="flex gap-2">
            <button
              disabled={pagination.offset === 0}
              onClick={() =>
                loadOrders(
                  pagination.limit,
                  Math.max(0, pagination.offset - pagination.limit),
                  type,
                )
              }
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              disabled={!pagination.has_more}
              onClick={() =>
                loadOrders(
                  pagination.limit,
                  pagination.offset + pagination.limit,
                  type,
                )
              }
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
