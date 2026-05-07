/**
 * Panel de pedidos de venta de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooSales } from '@/api/client'
import type { OdooSale } from '@/types/odoo'

const STATE_LABELS: Record<string, string> = {
  draft: 'Presupuesto',
  sent: 'Enviado',
  sale: 'Confirmado',
  done: 'Hecho',
  cancel: 'Cancelado',
}

const STATE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  sent: 'bg-blue-100 text-blue-800',
  sale: 'bg-green-100 text-green-800',
  done: 'bg-emerald-100 text-emerald-800',
  cancel: 'bg-red-100 text-red-800',
}

export default function OdooSales() {
  const [items, setItems] = useState<OdooSale[]>([])
  const [loading, setLoading] = useState(true)
  const [stateFilter, setStateFilter] = useState<string>('')
  const [pagination, setPagination] = useState({ limit: 10, offset: 0, total: 0, has_more: false })

  const load = async (limit = 10, offset = 0, s = stateFilter) => {
    setLoading(true)
    try {
      const data = await listOdooSales(limit, offset, s || undefined)
      setItems(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      console.error('Error cargando ventas Odoo:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const formatDate = (v: string | false) => v ? new Date(v).toLocaleDateString('es-ES') : '—'
  const formatAmount = (v: number, currency: [number, string] | false) => {
    const symbol = Array.isArray(currency) ? currency[1] : '€'
    return `${symbol} ${v.toFixed(2)}`
  }
  const formatField = (v: [number, string] | false) => v ? v[1] : '—'

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <select
          value={stateFilter}
          onChange={(e) => { setStateFilter(e.target.value); load(10, 0, e.target.value) }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">Todos los estados</option>
          {Object.entries(STATE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['Referencia', 'Cliente', 'Fecha', 'Estado', 'Total', 'Facturación'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Cargando...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Sin pedidos</td></tr>
            ) : items.map((o) => (
              <tr key={o.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{o.name}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(o.partner_id)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatDate(o.date_order)}</td>
                <td className="px-4 py-3 text-sm">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${STATE_COLORS[o.state] ?? 'bg-gray-100 text-gray-700'}`}>
                    {STATE_LABELS[o.state] ?? o.state}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-900">{formatAmount(o.amount_total, o.currency_id)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{o.invoice_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination.total > 0 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>{pagination.offset + 1}–{Math.min(pagination.offset + pagination.limit, pagination.total)} de {pagination.total}</div>
          <div className="flex gap-2">
            <button disabled={pagination.offset === 0} onClick={() => load(pagination.limit, Math.max(0, pagination.offset - pagination.limit))} className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50">Anterior</button>
            <button disabled={!pagination.has_more} onClick={() => load(pagination.limit, pagination.offset + pagination.limit)} className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50">Siguiente</button>
          </div>
        </div>
      )}
    </div>
  )
}
