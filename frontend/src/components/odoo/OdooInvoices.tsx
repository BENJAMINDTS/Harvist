/**
 * Panel de facturas de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooInvoices, validateOdooInvoice, cancelOdooInvoice } from '@/api/client'
import type { OdooInvoice, OdooInvoiceType } from '@/types/odoo'

const STATE_LABELS: Record<string, string> = {
  draft: 'Borrador',
  posted: 'Validada',
  cancel: 'Cancelada',
}

const STATE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  posted: 'bg-green-100 text-green-800',
  cancel: 'bg-red-100 text-red-800',
}

const PAYMENT_LABELS: Record<string, string> = {
  not_paid: 'No pagada',
  in_payment: 'En proceso',
  paid: 'Pagada',
  partial: 'Parcial',
  reversed: 'Revertida',
}

export default function OdooInvoices() {
  const [items, setItems] = useState<OdooInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [type, setType] = useState<OdooInvoiceType>('customer')
  const [pagination, setPagination] = useState({ limit: 10, offset: 0, total: 0, has_more: false })

  const load = async (limit = 10, offset = 0, t: OdooInvoiceType = type) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listOdooInvoices(t, limit, offset)
      setItems(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando facturas')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleType = (t: OdooInvoiceType) => { setType(t); load(10, 0, t) }

  const runAction = async (id: number, action: 'validate' | 'cancel') => {
    setActionLoading(id)
    setError(null)
    try {
      if (action === 'validate') await validateOdooInvoice(id)
      else await cancelOdooInvoice(id)
      load(pagination.limit, pagination.offset)
    } catch (err) {
      setError((err as Error).message ?? `Error al ${action === 'validate' ? 'validar' : 'cancelar'} factura`)
    } finally {
      setActionLoading(null)
    }
  }

  const formatDate = (v: string | false) => v ? new Date(v).toLocaleDateString('es-ES') : '—'
  const formatAmount = (v: number, currency: [number, string] | false) => {
    const symbol = Array.isArray(currency) ? currency[1] : '€'
    return `${symbol} ${v.toFixed(2)}`
  }
  const formatField = (v: [number, string] | false) => v ? v[1] : '—'

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {([
          { id: 'customer' as OdooInvoiceType, label: 'Facturas cliente' },
          { id: 'supplier' as OdooInvoiceType, label: 'Facturas proveedor' },
        ] as const).map((t) => (
          <button
            key={t.id}
            onClick={() => handleType(t.id)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors text-sm ${
              type === t.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Referencia</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Partner</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Fecha</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Estado</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Total</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Pendiente</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Pago</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={8} className="px-6 py-8 text-center text-gray-500">Cargando facturas...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={8} className="px-6 py-8 text-center text-gray-500">Sin facturas</td></tr>
            ) : items.map((inv) => (
              <tr key={inv.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{inv.name || `#${inv.id}`}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(inv.partner_id)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatDate(inv.invoice_date)}</td>
                <td className="px-6 py-4 text-sm">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${STATE_COLORS[inv.state] ?? 'bg-gray-100 text-gray-700'}`}>
                    {STATE_LABELS[inv.state] ?? inv.state}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-900">{formatAmount(inv.amount_total, inv.currency_id)}</td>
                <td className="px-6 py-4 text-sm text-gray-900">{formatAmount(inv.amount_residual, inv.currency_id)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">
                  {PAYMENT_LABELS[inv.payment_state] ?? inv.payment_state}
                </td>
                <td className="px-6 py-4 text-sm">
                  <div className="flex gap-2">
                    {inv.state === 'draft' && (
                      <button
                        onClick={() => runAction(inv.id, 'validate')}
                        disabled={actionLoading === inv.id}
                        className="text-green-600 hover:text-green-800 text-xs font-medium disabled:opacity-50"
                      >
                        Validar
                      </button>
                    )}
                    {inv.state !== 'cancel' && (
                      <button
                        onClick={() => runAction(inv.id, 'cancel')}
                        disabled={actionLoading === inv.id}
                        className="text-red-600 hover:text-red-800 text-xs font-medium disabled:opacity-50"
                      >
                        Cancelar
                      </button>
                    )}
                    {inv.state === 'cancel' && (
                      <span className="text-xs text-gray-400">—</span>
                    )}
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
    </div>
  )
}
