/**
 * Panel de gestión de marcas WooCommerce via atributo pa_brand.
 *
 * Permite CRUD de marcas (términos del atributo global "brand") y consultar
 * los productos asociados a cada marca.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import {
  listWordPressBrands,
  createWordPressBrand,
  updateWordPressBrand,
  deleteWordPressBrand,
  getWordPressBrandProducts,
  setWordPressProductBrand,
  listWordPressAllAttributes,
  configureWordPressBrandAttribute,
  getWordPressBrandAttribute,
} from '@/api/client'
import type { WooBrand, WooProduct } from '@/types/wordpress'

interface WooAttribute {
  id: number
  name: string
  slug: string
  term_count: number
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm'

type ModalMode = 'create' | 'edit' | 'products'

interface ModalState {
  mode: ModalMode
  brand?: WooBrand
}

export default function WordPressBrands() {
  const [brands, setBrands] = useState<WooBrand[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const [modal, setModal] = useState<ModalState | null>(null)
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [brandProducts, setBrandProducts] = useState<WooProduct[]>([])
  const [productsLoading, setProductsLoading] = useState(false)
  const [removingProductId, setRemovingProductId] = useState<number | null>(null)

  const [allAttributes, setAllAttributes] = useState<WooAttribute[]>([])
  const [currentAttr, setCurrentAttr] = useState<{ id: number; name: string; slug: string } | null>(null)
  const [showAttrConfig, setShowAttrConfig] = useState(false)
  const [selectedAttrId, setSelectedAttrId] = useState<number | ''>('')
  const [savingAttr, setSavingAttr] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const items = await listWordPressBrands()
      setBrands(items)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando marcas.')
    } finally {
      setLoading(false)
    }
  }

  const loadAttrInfo = async () => {
    try {
      const [attrs, current] = await Promise.all([
        listWordPressAllAttributes(),
        getWordPressBrandAttribute(),
      ])
      setAllAttributes(attrs)
      setCurrentAttr(current)
      setSelectedAttrId(current.id)
    } catch {
      // non-critical
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => { loadAttrInfo() }, [])

  const handleConfigureAttr = async () => {
    if (!selectedAttrId) return
    setSavingAttr(true)
    try {
      const updated = await configureWordPressBrandAttribute(Number(selectedAttrId))
      setCurrentAttr(updated)
      setShowAttrConfig(false)
      await load()
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error configurando el atributo.')
    } finally {
      setSavingAttr(false)
    }
  }

  const openCreate = () => {
    setFormName('')
    setFormDesc('')
    setFormError(null)
    setModal({ mode: 'create' })
  }

  const openEdit = (brand: WooBrand) => {
    setFormName(brand.name)
    setFormDesc(brand.description)
    setFormError(null)
    setModal({ mode: 'edit', brand })
  }

  const openProducts = async (brand: WooBrand) => {
    setModal({ mode: 'products', brand })
    setProductsLoading(true)
    setBrandProducts([])
    try {
      const items = await getWordPressBrandProducts(brand.id)
      setBrandProducts(items)
    } catch {
      setBrandProducts([])
    } finally {
      setProductsLoading(false)
    }
  }

  const handleRemoveProductFromBrand = async (product: WooProduct) => {
    if (!confirm(`¿Quitar la marca de "${product.name}"?`)) return
    setRemovingProductId(product.id)
    try {
      await setWordPressProductBrand(product.id, null)
      setBrandProducts((prev) => prev.filter((p) => p.id !== product.id))
      // Decrement count optimistically in the brands list
      setBrands((prev) =>
        prev.map((b) =>
          b.id === modal?.brand?.id ? { ...b, count: Math.max(0, b.count - 1) } : b,
        ),
      )
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error quitando la marca del producto.')
    } finally {
      setRemovingProductId(null)
    }
  }

  const closeModal = () => {
    setModal(null)
    setFormError(null)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) { setFormError('El nombre es obligatorio.'); return }
    setSaving(true)
    setFormError(null)
    try {
      if (modal?.mode === 'create') {
        const created = await createWordPressBrand(formName.trim(), formDesc.trim())
        setBrands((prev) => [...prev, created])
      } else if (modal?.mode === 'edit' && modal.brand) {
        const updated = await updateWordPressBrand(modal.brand.id, {
          name: formName.trim(),
          description: formDesc.trim(),
        })
        setBrands((prev) => prev.map((b) => (b.id === updated.id ? updated : b)))
      }
      closeModal()
    } catch (err: unknown) {
      setFormError((err as { message?: string })?.message ?? 'Error guardando marca.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (brand: WooBrand) => {
    if (!confirm(`¿Eliminar la marca "${brand.name}"? Esta acción no se puede deshacer.`)) return
    try {
      await deleteWordPressBrand(brand.id)
      setBrands((prev) => prev.filter((b) => b.id !== brand.id))
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error eliminando marca.')
    }
  }

  const filtered = search
    ? brands.filter((b) => b.name.toLowerCase().includes(search.toLowerCase()))
    : brands

  return (
    <div className="space-y-4">
      {/* Attribute config banner */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm">
        <span className="text-gray-600">
          Atributo activo:
          {currentAttr
            ? <strong className="ml-1 text-gray-900">{currentAttr.name} ({currentAttr.slug})</strong>
            : <span className="ml-1 text-gray-400">detectando…</span>}
        </span>
        <button
          onClick={() => setShowAttrConfig((v) => !v)}
          className="ml-auto text-xs text-purple-600 hover:text-purple-800 font-medium"
        >
          {showAttrConfig ? '▲ Cerrar' : '⚙ Cambiar atributo'}
        </button>
      </div>

      {/* Attribute selector panel */}
      {showAttrConfig && (
        <div className="border border-purple-200 bg-purple-50 rounded-lg p-4 space-y-3">
          <p className="text-sm text-gray-700 font-medium">
            Selecciona el atributo de WooCommerce donde están tus marcas:
          </p>
          {allAttributes.length === 0 ? (
            <p className="text-sm text-gray-400">Cargando atributos...</p>
          ) : (
            <div className="flex gap-2 flex-wrap items-end">
              <select
                value={selectedAttrId}
                onChange={(e) => setSelectedAttrId(e.target.value ? Number(e.target.value) : '')}
                className={`${INPUT_CLS} max-w-xs`}
              >
                <option value="">— Selecciona un atributo —</option>
                {allAttributes.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.slug}) — {a.term_count} términos
                  </option>
                ))}
              </select>
              <button
                onClick={handleConfigureAttr}
                disabled={!selectedAttrId || savingAttr}
                className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium disabled:opacity-50"
              >
                {savingAttr ? 'Guardando…' : 'Aplicar'}
              </button>
            </div>
          )}
          <p className="text-xs text-gray-500">
            Busca el atributo que contiene tus marcas (e.g. "Marca", "Brand"). La selección se guarda en el servidor.
          </p>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder="Buscar marca..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm w-48 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        />
        <button
          onClick={load}
          disabled={loading}
          className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          ↻ Refrescar
        </button>
        <button
          onClick={openCreate}
          className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium"
        >
          + Nueva marca
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Tabla */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {['ID', 'Nombre', 'Slug', 'Descripción', 'Productos', 'Acciones'].map((h) => (
                <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  Cargando marcas...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  {search ? 'Sin resultados.' : 'No hay marcas. Crea la primera.'}
                </td>
              </tr>
            ) : (
              filtered.map((brand) => (
                <tr key={brand.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-500">{brand.id}</td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{brand.name}</td>
                  <td className="px-6 py-4 text-sm font-mono text-gray-500">{brand.slug}</td>
                  <td className="px-6 py-4 text-sm text-gray-600 max-w-xs truncate">
                    {brand.description || <span className="text-gray-400 italic">—</span>}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => openProducts(brand)}
                      className="text-purple-600 hover:text-purple-800 text-xs font-medium"
                    >
                      {brand.count} productos →
                    </button>
                  </td>
                  <td className="px-6 py-4 text-sm flex gap-3">
                    <button
                      onClick={() => openEdit(brand)}
                      className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(brand)}
                      className="text-red-600 hover:text-red-800 text-xs font-medium"
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal crear / editar */}
      {modal && (modal.mode === 'create' || modal.mode === 'edit') && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">
                {modal.mode === 'create' ? 'Nueva marca' : `Editar: ${modal.brand?.name}`}
              </h3>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>
            <div className="px-6 py-4">
              <form onSubmit={handleSave} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Nombre *</label>
                  <input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className={INPUT_CLS}
                    placeholder="Ej: Nike, Adidas..."
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Descripción</label>
                  <textarea
                    rows={3}
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    className={`${INPUT_CLS} resize-none`}
                    placeholder="Descripción opcional de la marca"
                  />
                </div>
              </form>
            </div>
            <div className="px-6 py-4 border-t border-gray-200 space-y-3">
              {formError && <p className="text-sm text-red-600">{formError}</p>}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={closeModal}
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium"
                >
                  {saving ? 'Guardando...' : modal.mode === 'create' ? 'Crear' : 'Guardar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal productos de la marca */}
      {modal?.mode === 'products' && modal.brand && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">
                Productos — {modal.brand.name}
              </h3>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {productsLoading ? (
                <div className="p-8 text-center text-gray-500">Cargando productos...</div>
              ) : brandProducts.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  No hay productos con esta marca.
                </div>
              ) : (
                <table className="w-full">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      {['ID', 'Nombre', 'SKU', 'Precio', 'Stock', 'Estado', 'Acciones'].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-3 text-left text-xs font-semibold text-gray-700"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {brandProducts.map((p) => (
                      <tr key={p.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm text-gray-500">{p.id}</td>
                        <td className="px-4 py-3 text-sm font-medium text-gray-900">{p.name}</td>
                        <td className="px-4 py-3 text-sm font-mono text-gray-500">{p.sku || '—'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600">
                          {p.price ? `${p.price} €` : '—'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600">
                          {p.stock_quantity ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <span
                            className={`px-2 py-1 rounded text-xs font-medium ${
                              p.status === 'publish'
                                ? 'bg-green-100 text-green-800'
                                : 'bg-gray-100 text-gray-600'
                            }`}
                          >
                            {p.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <button
                            onClick={() => handleRemoveProductFromBrand(p)}
                            disabled={removingProductId === p.id}
                            className="text-red-600 hover:text-red-800 text-xs font-medium disabled:opacity-50"
                          >
                            {removingProductId === p.id ? 'Quitando…' : 'Quitar marca'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-200">
              <button
                onClick={closeModal}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
