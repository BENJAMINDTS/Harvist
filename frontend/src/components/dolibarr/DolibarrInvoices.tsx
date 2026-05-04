/**
 * Módulo de gestión de facturas de Dolibarr.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { listDolibarrInvoices } from '@/api/client'
import { type DolibarrInvoice, type InvoiceType } from '@/types/dolibarr'

export default function DolibarrInvoices() {
  const [invoices, setInvoices] = useState<DolibarrInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [type, setType] = useState<InvoiceType>('customer')
  const [pagination, setPagination] = useState({
    limit: 10,
    offset: 0,
    total: 0,
    has_more: false,
  })

  const loadInvoices = async (
    limit = 10,
    offset = 0,
    selectedType: InvoiceType = type,
  ) => {
    try {
      setLoading(true)
      const data = await listDolibarrInvoices(selectedType, limit, offset)
      setInvoices(data.items)
      setPagination({
        limit: data.limit,
        offset: data.offset,
        total: data.total,
        has_more: data.has_more,
      })
    } catch (err) {
      console.error('Error loading invoices:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInvoices()
  }, [])

  const handleTypeChange = (newType: InvoiceType) => {
    setType(newType)
    loadInvoices(10, 0, newType)
  }

  const getStatusLabel = (status: number): string => {
    const statusMap: Record<number, string> = {
      0: 'Borrador',
      1: 'Validada',
      2: 'Pagada',
      3: 'Cancelada',
    }
    return statusMap[status] ?? `Estado ${status}`
  }

  const formatDate = (timestamp: number): string => {
    return new Date(timestamp * 1000).toLocaleDateString('es-ES')
  }

  return (
    <div className="space-y-6">
      {/* Toggle tipo */}
      <div className="flex gap-2">
        {(
          [
            { id: 'customer' as InvoiceType, label: 'Facturas de cliente' },
            { id: 'supplier' as InvoiceType, label: 'Facturas de proveedor' },
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
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Pendiente
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  Cargando...
                </td>
              </tr>
            ) : invoices.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  Sin facturas
                </td>
              </tr>
            ) : (
              invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    {inv.ref}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{inv.socid}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {formatDate(inv.date)}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span className="px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-800">
                      {getStatusLabel(inv.statut)}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    €{inv.total_ttc.toFixed(2)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    €{inv.remaintopay.toFixed(2)}
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
                loadInvoices(
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
                loadInvoices(
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
