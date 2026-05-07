/**
 * Panel de productos de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooProducts } from '@/api/client'
import type { OdooProduct } from '@/types/odoo'

export default function OdooProducts() {
  const [products, setProducts] = useState<OdooProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [pagination, setPagination] = useState({
    limit: 10,
    offset: 0,
    total: 0,
    has_more: false,
  })

  const load = async (limit = 10, offset = 0, q = search) => {
    setLoading(true)
    try {
      const data = await listOdooProducts(limit, offset, q)
      setProducts(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      console.error('Error cargando productos Odoo:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const formatPrice = (v: number) => `€${v.toFixed(2)}`

  const formatField = (v: [number, string] | false | string | undefined) => {
    if (!v) return '—'
    if (Array.isArray(v)) return v[1]
    return String(v)
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && load(10, 0, search)}
          placeholder="Buscar por nombre..."
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm"
        />
        <button
          onClick={() => load(10, 0, search)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700"
        >
          Buscar
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['ID', 'Referencia', 'Nombre', 'Categoría', 'Precio', 'Stock', 'Activo'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">Cargando...</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">Sin productos</td></tr>
            ) : products.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm text-gray-500">{p.id}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(p.default_code)}</td>
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{p.name}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(p.categ_id)}</td>
                <td className="px-4 py-3 text-sm text-gray-900">{formatPrice(p.list_price)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{p.qty_available.toFixed(0)}</td>
                <td className="px-4 py-3 text-sm">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${p.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                    {p.active ? 'Sí' : 'No'}
                  </span>
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
