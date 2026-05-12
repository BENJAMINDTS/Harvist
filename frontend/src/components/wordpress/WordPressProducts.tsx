/**
 * Panel de gestión de productos WooCommerce.
 * Lista, crea, edita y elimina productos. Sincroniza desde job Harvist.
 *
 * @author Carlos Vico
 */
import { useEffect, useState } from 'react'
import {
  listWordPressProducts,
  deleteWordPressProduct,
  createWordPressProduct,
  updateWordPressProduct,
} from '@/api/client'
import type { WooProduct } from '@/types/wordpress'

const STATUS_COLORS: Record<string, string> = {
  publish: 'bg-green-100 text-green-800',
  draft: 'bg-gray-100 text-gray-700',
  private: 'bg-yellow-100 text-yellow-800',
  pending: 'bg-blue-100 text-blue-800',
}

const STOCK_COLORS: Record<string, string> = {
  instock: 'text-green-600',
  outofstock: 'text-red-600',
  onbackorder: 'text-yellow-600',
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm'

export default function WordPressProducts() {
  const [products, setProducts] = useState<WooProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('any')
  const [editProduct, setEditProduct] = useState<WooProduct | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const limit = 50

  const [formName, setFormName] = useState('')
  const [formSku, setFormSku] = useState('')
  const [formPrice, setFormPrice] = useState('')
  const [formStatus, setFormStatus] = useState<'publish' | 'draft'>('publish')
  const [formStock, setFormStock] = useState('')
  const [formDesc, setFormDesc] = useState('')

  const load = async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const items = await listWordPressProducts(limit, newOffset, statusFilter)
      setProducts(items)
      setOffset(newOffset)
      setHasMore(items.length === limit)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando productos.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [statusFilter])

  const handleDelete = async (p: WooProduct) => {
    if (!confirm(`¿Eliminar "${p.name}" (ID ${p.id})?`)) return
    try {
      await deleteWordPressProduct(p.id)
      setProducts((prev) => prev.filter((x) => x.id !== p.id))
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error eliminando producto.')
    }
  }

  const openCreate = () => {
    setEditProduct(null)
    setFormName(''); setFormSku(''); setFormPrice('')
    setFormStatus('publish'); setFormStock(''); setFormDesc('')
    setFormError(null); setShowForm(true)
  }

  const openEdit = (p: WooProduct) => {
    setEditProduct(p)
    setFormName(p.name); setFormSku(p.sku); setFormPrice(p.regular_price)
    setFormStatus(p.status === 'publish' ? 'publish' : 'draft')
    setFormStock(p.stock_quantity != null ? String(p.stock_quantity) : '')
    setFormDesc(p.description)
    setFormError(null); setShowForm(true)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName) { setFormError('El nombre es obligatorio.'); return }
    setSaving(true); setFormError(null)
    try {
      const data: Partial<WooProduct> = {
        name: formName,
        sku: formSku,
        regular_price: formPrice,
        status: formStatus,
        description: formDesc,
        manage_stock: formStock !== '',
        stock_quantity: formStock !== '' ? parseInt(formStock, 10) : null,
      }
      if (editProduct) {
        await updateWordPressProduct(editProduct.id, data)
      } else {
        await createWordPressProduct(data)
      }
      setShowForm(false)
      await load(offset)
    } catch (err: unknown) {
      setFormError((err as { message?: string })?.message ?? 'Error guardando producto.')
    } finally {
      setSaving(false)
    }
  }

  const filtered = search
    ? products.filter(
        (p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.sku.toLowerCase().includes(search.toLowerCase()),
      )
    : products

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex gap-2 flex-wrap">
        <input
          type="text"
          placeholder="Buscar por nombre o SKU…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-48 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        />
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setOffset(0) }}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        >
          <option value="any">Todos</option>
          <option value="publish">Publicados</option>
          <option value="draft">Borrador</option>
          <option value="private">Privados</option>
        </select>
        <button
          onClick={() => load(offset)}
          disabled={loading}
          className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
        >
          ↻ Refrescar
        </button>
        <button
          onClick={openCreate}
          className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium"
        >
          + Nuevo producto
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['ID', 'Nombre', 'SKU', 'Precio', 'Stock', 'Estado', 'Acciones'].map((h) => (
                <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                  Cargando productos...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                  Sin resultados.
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-500">{p.id}</td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900 max-w-48 truncate">{p.name}</td>
                  <td className="px-6 py-4 text-sm font-mono text-gray-600">{p.sku || '—'}</td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    {p.regular_price ? `${p.regular_price} €` : '—'}
                  </td>
                  <td className={`px-6 py-4 text-sm font-medium ${STOCK_COLORS[p.stock_status] ?? ''}`}>
                    {p.manage_stock ? (p.stock_quantity ?? 0) : p.stock_status}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${STATUS_COLORS[p.status] ?? ''}`}>
                      {p.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <div className="flex gap-3">
                      <button
                        onClick={() => openEdit(p)}
                        className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(p)}
                        className="text-red-600 hover:text-red-800 text-xs font-medium"
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-end gap-2 text-sm text-gray-600">
        <button
          onClick={() => load(Math.max(0, offset - limit))}
          disabled={offset === 0 || loading}
          className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          onClick={() => load(offset + limit)}
          disabled={!hasMore || loading}
          className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>

      {/* Modal Form */}
      {showForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">
                {editProduct ? `Editar producto #${editProduct.id}` : 'Nuevo producto'}
              </h3>
              <button
                onClick={() => setShowForm(false)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-4">
              <form onSubmit={handleSave} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Nombre *</label>
                  <input value={formName} onChange={(e) => setFormName(e.target.value)} className={INPUT_CLS} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">SKU</label>
                    <input value={formSku} onChange={(e) => setFormSku(e.target.value)} className={`${INPUT_CLS} font-mono`} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Precio regular (€)</label>
                    <input type="number" step="0.01" value={formPrice} onChange={(e) => setFormPrice(e.target.value)} className={INPUT_CLS} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Estado</label>
                    <select value={formStatus} onChange={(e) => setFormStatus(e.target.value as 'publish' | 'draft')} className={INPUT_CLS}>
                      <option value="publish">Publicado</option>
                      <option value="draft">Borrador</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Stock</label>
                    <input type="number" value={formStock} onChange={(e) => setFormStock(e.target.value)} placeholder="Sin gestión" className={INPUT_CLS} />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Descripción</label>
                  <textarea rows={3} value={formDesc} onChange={(e) => setFormDesc(e.target.value)} className={`${INPUT_CLS} resize-none`} />
                </div>
              </form>
            </div>
            <div className="px-6 py-4 border-t border-gray-200 space-y-3 flex-shrink-0">
              {formError && (
                <p className="text-sm text-red-600">{formError}</p>
              )}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium"
                >
                  {saving ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
