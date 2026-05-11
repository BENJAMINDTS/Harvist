/**
 * Panel de clientes WooCommerce.
 *
 * @author Carlos Vico
 */
import { useEffect, useState } from 'react'
import { listWordPressCustomers, deleteWordPressCustomer } from '@/api/client'
import type { WooCustomer } from '@/types/wordpress'

export default function WordPressCustomers() {
  const [customers, setCustomers] = useState<WooCustomer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const limit = 50

  const load = async (newOffset = 0, searchTerm = search) => {
    setLoading(true)
    setError(null)
    try {
      const items = await listWordPressCustomers(limit, newOffset, searchTerm)
      setCustomers(items)
      setOffset(newOffset)
      setHasMore(items.length === limit)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando clientes.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    load(0, searchInput)
  }

  const handleDelete = async (c: WooCustomer) => {
    if (!confirm(`¿Eliminar cliente "${c.email}"?`)) return
    try {
      await deleteWordPressCustomer(c.id)
      setCustomers((prev) => prev.filter((x) => x.id !== c.id))
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error eliminando cliente.')
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          placeholder="Buscar por nombre o email…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        />
        <button type="submit" className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium">Buscar</button>
        <button type="button" onClick={() => load(offset)} disabled={loading} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">↻</button>
      </form>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['ID', 'Nombre', 'Email', 'Pedidos', 'Total gastado', 'Registro', 'Acciones'].map((h) => (
                <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Cargando clientes...</td></tr>
            ) : customers.length === 0 ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Sin clientes.</td></tr>
            ) : customers.map((c) => (
              <tr key={c.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm text-gray-500">{c.id}</td>
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{c.first_name} {c.last_name}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{c.email}</td>
                <td className="px-6 py-4 text-sm text-gray-700">{c.orders_count}</td>
                <td className="px-6 py-4 text-sm text-gray-700">{c.total_spent} €</td>
                <td className="px-6 py-4 text-sm text-gray-500">{new Date(c.date_created).toLocaleDateString('es-ES')}</td>
                <td className="px-6 py-4 text-sm">
                  <button onClick={() => handleDelete(c)} className="text-red-600 hover:text-red-800 text-xs font-medium">Eliminar</button>
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
    </div>
  )
}
