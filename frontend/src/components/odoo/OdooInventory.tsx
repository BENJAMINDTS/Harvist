/**
 * Panel de inventario/stock de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooStock } from '@/api/client'
import type { OdooStockLine } from '@/types/odoo'

export default function OdooInventory() {
  const [items, setItems] = useState<OdooStockLine[]>([])
  const [loading, setLoading] = useState(true)
  const [pagination, setPagination] = useState({ limit: 50, offset: 0, total: 0, has_more: false })

  const load = async (limit = 50, offset = 0) => {
    setLoading(true)
    try {
      const data = await listOdooStock(limit, offset)
      setItems(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      console.error('Error cargando stock Odoo:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const formatField = (v: [number, string] | false) => v ? v[1] : '—'

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['Producto', 'Ubicación', 'Cantidad', 'Reservada', 'Disponible'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">Cargando...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">Sin stock</td></tr>
            ) : items.map((s) => (
              <tr key={s.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{formatField(s.product_id)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(s.location_id)}</td>
                <td className="px-4 py-3 text-sm text-gray-900">{s.quantity.toFixed(2)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{s.reserved_quantity.toFixed(2)}</td>
                <td className="px-4 py-3 text-sm text-gray-900 font-medium">
                  {(s.quantity - s.reserved_quantity).toFixed(2)}
                </td>
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
