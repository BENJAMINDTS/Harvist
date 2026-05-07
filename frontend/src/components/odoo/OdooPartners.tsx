/**
 * Panel de partners (clientes/proveedores) de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooPartners } from '@/api/client'
import type { OdooPartner, PartnerMode } from '@/types/odoo'

export default function OdooPartners() {
  const [partners, setPartners] = useState<OdooPartner[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<PartnerMode>('all')
  const [search, setSearch] = useState('')
  const [pagination, setPagination] = useState({ limit: 10, offset: 0, total: 0, has_more: false })

  const load = async (limit = 10, offset = 0, m: PartnerMode = mode, q = search) => {
    setLoading(true)
    try {
      const data = await listOdooPartners(m, limit, offset, q)
      setPartners(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      console.error('Error cargando partners Odoo:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleMode = (m: PartnerMode) => { setMode(m); load(10, 0, m) }

  const formatField = (v: [number, string] | false | string | undefined) => {
    if (!v) return '—'
    if (Array.isArray(v)) return v[1]
    return String(v)
  }

  const modes: { id: PartnerMode; label: string }[] = [
    { id: 'all', label: 'Todos' },
    { id: 'customer', label: 'Clientes' },
    { id: 'supplier', label: 'Proveedores' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => handleMode(m.id)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors text-sm ${mode === m.id ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
          >
            {m.label}
          </button>
        ))}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && load(10, 0, mode, search)}
          placeholder="Buscar por nombre..."
          className="flex-1 min-w-40 border border-gray-300 rounded-lg px-3 py-2 text-sm"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['ID', 'Nombre', 'Email', 'Teléfono', 'Ciudad', 'NIF', 'Tipo'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">Cargando...</td></tr>
            ) : partners.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">Sin partners</td></tr>
            ) : partners.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm text-gray-500">{p.id}</td>
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{p.name}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(p.email)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(p.phone)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(p.city)}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{formatField(p.vat)}</td>
                <td className="px-4 py-3 text-sm">
                  <div className="flex gap-1">
                    {p.customer_rank > 0 && <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">Cliente</span>}
                    {p.supplier_rank > 0 && <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">Proveedor</span>}
                  </div>
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
