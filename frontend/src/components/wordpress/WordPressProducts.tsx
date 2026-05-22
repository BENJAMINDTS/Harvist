/**
 * Panel de gestión de productos WooCommerce.
 * Lista, crea, edita y elimina productos. El formulario de creación/edición
 * incluye todos los campos equivalentes a Dolibarr: nombre, SKU, slug, tipo,
 * precios, descripciones, stock, peso, dimensiones, marca y categorías.
 *
 * @author Carlos Vico | BenjaminDTS
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listWordPressProducts,
  deleteWordPressProduct,
  deleteWordPressProducts,
  createWordPressProduct,
  updateWordPressProduct,
  listWordPressBrands,
  getWordPressBrandAttribute,
  listWordPressCategories,
  getWordPressCsvFields,
  previewWordPressCsv,
  importWordPressCsv,
  getWordPressImportStatus,
  getWordPressCategoryTree,
  syncWordPressAllToDolibarr,
} from '@/api/client'
import type {
  WooProduct,
  WooProductAttribute,
  WooBrand,
  WooBrandAttributeInfo,
  WooCategory,
  WcImportField,
  WpImportTask,
} from '@/types/wordpress'

/** Aplana el árbol de categorías en orden depth-first añadiendo el nivel de indentación. */
function flattenCategoryTree(
  nodes: WooCategory[],
  level = 0,
): Array<WooCategory & { level: number }> {
  const result: Array<WooCategory & { level: number }> = []
  for (const node of nodes) {
    result.push({ ...node, level })
    if (node.children?.length) {
      result.push(...flattenCategoryTree(node.children, level + 1))
    }
  }
  return result
}

const getPaginationItems = (currentPage: number, totalPages: number): (number | string)[] => {
  if (!isFinite(totalPages) || totalPages <= 0) return []
  const delta = 2
  const left = currentPage - delta
  const right = currentPage + delta + 1
  const range: number[] = []
  const rangeWithDots: (number | string)[] = []
  let l: number | undefined
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= left && i < right)) range.push(i)
  }
  for (const i of range) {
    if (l) {
      if (i - l === 2) rangeWithDots.push(l + 1)
      else if (i - l !== 1) rangeWithDots.push('...')
    }
    rangeWithDots.push(i)
    l = i
  }
  return rangeWithDots
}

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

const SECTION_LABEL = 'text-xs font-semibold text-purple-700 uppercase tracking-wide mb-2 mt-4 border-b border-purple-100 pb-1'

/** Redondea a 2 decimales máximo. Para display: quita ceros finales. Para payload: mantiene 2 decimales. */
function toPrice(v: string, forPayload = false): string {
  if (v === '') return ''
  const n = parseFloat(v)
  if (isNaN(n)) return ''
  const fixed = n.toFixed(2)
  return forPayload ? fixed : parseFloat(fixed).toString()
}

/** Extrae el nombre de la marca: campo nativo brands[] primero, luego atributos. */
function getProductBrandName(product: WooProduct): string {
  if (product.brands?.length) return product.brands[0].name
  const attr = product.attributes?.find(
    (a) => a.slug === 'pa_brand' || a.slug === 'brand' || a.slug === 'pa_marca' || a.slug === 'marca',
  )
  return attr?.options?.[0] ?? '—'
}

export default function WordPressProducts() {
  const [products, setProducts] = useState<WooProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('any')
  const [editProduct, setEditProduct] = useState<WooProduct | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [showCsvModal, setShowCsvModal] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // ── Paginación ─────────────────────────────────────────────────────────────
  const [pagination, setPagination] = useState({ limit: 10, offset: 0, total: 0, has_more: false })
  const [customPageSize, setCustomPageSize] = useState('')
  const [showCustomPageSizeInput, setShowCustomPageSizeInput] = useState(false)
  const [goToPageInput, setGoToPageInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Selección masiva ────────────────────────────────────────────────────────
  const [selectedProductIds, setSelectedProductIds] = useState<Set<number>>(new Set())

  // ── Sync masivo a Dolibarr ─────────────────────────────────────────────────
  const [syncingToDoli, setSyncingToDoli] = useState(false)
  const [syncToDoliResult, setSyncToDoliResult] = useState<{ created: number; updated: number; errors: number } | null>(null)

  // ── Campos del formulario ──────────────────────────────────────────────────
  // Información básica
  const [formName, setFormName] = useState('')
  const [formSku, setFormSku] = useState('')
  const [formSlug, setFormSlug] = useState('')
  const [formType, setFormType] = useState<WooProduct['type']>('simple')
  const [formStatus, setFormStatus] = useState<'publish' | 'draft'>('publish')

  // Precios
  const [formPrice, setFormPrice] = useState('')
  const [formSalePrice, setFormSalePrice] = useState('')

  // Descripciones
  const [formShortDesc, setFormShortDesc] = useState('')
  const [formDesc, setFormDesc] = useState('')

  // Stock
  const [formManageStock, setFormManageStock] = useState(false)
  const [formStock, setFormStock] = useState('')
  const [formStockStatus, setFormStockStatus] = useState<WooProduct['stock_status']>('instock')

  // Datos físicos
  const [formWeight, setFormWeight] = useState('')
  const [formLength, setFormLength] = useState('')
  const [formWidth, setFormWidth] = useState('')
  const [formHeight, setFormHeight] = useState('')

  // Clasificación
  const [formBrandId, setFormBrandId] = useState<number | null>(null)
  const [formOtherAttrs, setFormOtherAttrs] = useState<WooProductAttribute[]>([])
  const [formCategoryIds, setFormCategoryIds] = useState<number[]>([])

  // ── Datos auxiliares ───────────────────────────────────────────────────────
  const [brands, setBrands] = useState<WooBrand[]>([])
  const [brandAttrInfo, setBrandAttrInfo] = useState<WooBrandAttributeInfo | null>(null)
  const [categories, setCategories] = useState<WooCategory[]>([])
  const [categoryTree, setCategoryTree] = useState<Array<WooCategory & { level: number }>>([])

  const loadProducts = useCallback(async (limit = 10, offset = 0, query = '', status = statusFilter) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listWordPressProducts(limit, offset, status, query)
      setProducts(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando productos.')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  const loadAuxData = async () => {
    // Promise.allSettled so a failure in one call doesn't silently block the others.
    const [brandResult, attrResult, catResult, treeResult] = await Promise.allSettled([
      listWordPressBrands(),
      getWordPressBrandAttribute(),
      listWordPressCategories(),
      getWordPressCategoryTree(),
    ])
    if (brandResult.status === 'fulfilled') setBrands(brandResult.value)
    if (attrResult.status === 'fulfilled') setBrandAttrInfo(attrResult.value)
    if (catResult.status === 'fulfilled') setCategories(catResult.value)
    if (treeResult.status === 'fulfilled') setCategoryTree(flattenCategoryTree(treeResult.value))
  }

  useEffect(() => { loadProducts(pagination.limit, 0, searchQuery, statusFilter) }, [statusFilter])
  useEffect(() => { loadProducts() }, [])
  useEffect(() => { loadAuxData() }, [])

  // ── Paginación ─────────────────────────────────────────────────────────────

  const handlePageSizeChange = (newSize: number | string): void => {
    if (newSize === 'custom') {
      setShowCustomPageSizeInput(true)
      setCustomPageSize(String(pagination.limit))
    } else {
      setShowCustomPageSizeInput(false)
      const size = Number(newSize)
      if (size > 0) loadProducts(size, 0, searchQuery)
    }
  }

  const handleApplyCustomPageSize = (): void => {
    const size = parseInt(customPageSize, 10)
    if (!size || size <= 0) return
    setShowCustomPageSizeInput(false)
    loadProducts(size, 0, searchQuery)
  }

  const handlePageChange = useCallback((pageNumber: number): void => {
    const newOffset = pageNumber * pagination.limit
    loadProducts(pagination.limit, newOffset, searchQuery)
    setGoToPageInput('')
  }, [pagination.limit, loadProducts, searchQuery])

  const handleGoToPage = useCallback((): void => {
    const pageNum = parseInt(goToPageInput, 10)
    const totalPages = Math.ceil(pagination.total / pagination.limit)
    if (!isNaN(pageNum) && pageNum >= 1 && pageNum <= totalPages) {
      handlePageChange(pageNum - 1)
    } else {
      alert(`Introduce un número de página válido entre 1 y ${totalPages}.`)
    }
  }, [goToPageInput, pagination.limit, pagination.total, handlePageChange])

  const handleSearchChange = (query: string): void => {
    setSearchQuery(query)
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current)
    searchTimeoutRef.current = setTimeout(() => loadProducts(pagination.limit, 0, query), 300)
  }

  // ── Selección masiva ────────────────────────────────────────────────────────

  const handleSelectProduct = useCallback((productId: number, isSelected: boolean): void => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      if (isSelected) next.add(productId)
      else next.delete(productId)
      return next
    })
  }, [])

  const handleSelectAll = useCallback((isChecked: boolean): void => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      if (isChecked) products.forEach((p) => next.add(p.id))
      else products.forEach((p) => next.delete(p.id))
      return next
    })
  }, [products])

  const handleDeleteSelected = useCallback(async (): Promise<void> => {
    if (selectedProductIds.size === 0) return
    if (!confirm(`¿Eliminar ${selectedProductIds.size} productos seleccionados? Esta acción no se puede deshacer.`)) return
    setLoading(true); setError(null)
    try {
      await deleteWordPressProducts(Array.from(selectedProductIds))
      setSelectedProductIds(new Set())
      loadProducts(pagination.limit, pagination.offset, searchQuery)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error eliminando productos seleccionados.')
    } finally {
      setLoading(false)
    }
  }, [selectedProductIds, loadProducts, pagination.limit, pagination.offset, searchQuery])

  const handleDelete = async (p: WooProduct): Promise<void> => {
    if (!confirm(`¿Eliminar "${p.name}" (ID ${p.id})?`)) return
    try {
      await deleteWordPressProduct(p.id)
      setSelectedProductIds((prev) => { const next = new Set(prev); next.delete(p.id); return next })
      loadProducts(pagination.limit, pagination.offset, searchQuery)
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error eliminando producto.')
    }
  }

  const handleSyncAllToDolibarr = async (): Promise<void> => {
    if (!confirm('¿Sincronizar todos los productos de WooCommerce a Dolibarr? Se crearán o actualizarán por SKU/ref.')) return
    setSyncingToDoli(true)
    setSyncToDoliResult(null)
    try {
      const result = await syncWordPressAllToDolibarr()
      setSyncToDoliResult({ created: result.created, updated: result.updated, errors: result.errors })
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error en sync masivo a Dolibarr')
    } finally {
      setSyncingToDoli(false)
    }
  }

  const resetForm = () => {
    setFormName(''); setFormSku(''); setFormSlug(''); setFormType('simple')
    setFormStatus('publish'); setFormPrice(''); setFormSalePrice('')
    setFormShortDesc(''); setFormDesc('')
    setFormManageStock(false); setFormStock(''); setFormStockStatus('instock')
    setFormWeight(''); setFormLength(''); setFormWidth(''); setFormHeight('')
    setFormBrandId(null); setFormOtherAttrs([]); setFormCategoryIds([])
    setFormError(null)
  }

  const openCreate = () => {
    setEditProduct(null)
    resetForm()
    setShowForm(true)
  }

  const openEdit = (p: WooProduct) => {
    setEditProduct(p)
    setFormName(p.name)
    setFormSku(p.sku)
    setFormSlug(p.slug)
    setFormType(p.type ?? 'simple')
    setFormStatus(p.status === 'publish' ? 'publish' : 'draft')
    setFormPrice(p.regular_price)
    setFormSalePrice(p.sale_price ?? '')
    setFormShortDesc(p.short_description ?? '')
    setFormDesc(p.description)
    setFormManageStock(p.manage_stock)
    setFormStock(p.stock_quantity != null ? String(p.stock_quantity) : '')
    setFormStockStatus(p.stock_status ?? 'instock')
    setFormWeight(p.weight ?? '')
    setFormLength(p.dimensions?.length ?? '')
    setFormWidth(p.dimensions?.width ?? '')
    setFormHeight(p.dimensions?.height ?? '')
    setFormCategoryIds(p.categories?.map((c) => c.id) ?? [])
    // Marca
    if (brandAttrInfo?.use_native) {
      setFormBrandId(p.brands?.[0]?.id ?? null)
    } else {
      const brandAttr = p.attributes?.find(
        (a) => a.slug === 'pa_brand' || a.slug === 'brand' || a.slug === 'pa_marca' || a.slug === 'marca',
      )
      const matched = brands.find((b) => b.name === (brandAttr?.options[0] ?? ''))
      setFormBrandId(matched?.id ?? null)
    }
    const brandSlugs = new Set(['pa_brand', 'brand', 'pa_marca', 'marca'])
    setFormOtherAttrs(p.attributes?.filter((a) => !brandSlugs.has(a.slug)) ?? [])
    setFormError(null)
    setShowForm(true)
  }

  const buildAttributesPayload = (): WooProductAttribute[] => {
    const attrs: WooProductAttribute[] = [...formOtherAttrs]
    const attrId = brandAttrInfo?.id
    if (attrId && formBrandId !== null) {
      const selectedBrand = brands.find((b) => b.id === formBrandId)
      if (selectedBrand) {
        attrs.push({
          id: attrId,
          name: 'Marca',
          slug: 'pa_brand',
          position: attrs.length,
          visible: true,
          variation: false,
          options: [selectedBrand.name],
        })
      }
    }
    return attrs
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName) { setFormError('El nombre es obligatorio.'); return }
    setSaving(true); setFormError(null)
    try {
      const brandPayload = brandAttrInfo?.use_native
        ? { brands: (formBrandId !== null ? [{ id: formBrandId }] : []) as WooProduct['brands'] }
        : { attributes: buildAttributesPayload() }

      const selectedCategories = formCategoryIds
        .map((id) => categories.find((c) => c.id === id))
        .filter((c): c is WooCategory => c !== undefined)
        .map((c) => ({ id: c.id, name: c.name, slug: c.slug }))

      const hasDimensions = formLength !== '' || formWidth !== '' || formHeight !== ''

      const data: Partial<WooProduct> = {
        name: formName,
        sku: formSku,
        ...(formSlug ? { slug: formSlug } : {}),
        type: formType,
        regular_price: toPrice(formPrice, true),
        sale_price: toPrice(formSalePrice, true),
        status: formStatus,
        description: formDesc,
        short_description: formShortDesc,
        weight: formWeight,
        ...(hasDimensions ? { dimensions: { length: formLength, width: formWidth, height: formHeight } } : {}),
        manage_stock: formManageStock,
        stock_quantity: formManageStock && formStock !== '' ? parseInt(formStock, 10) : null,
        stock_status: formStockStatus,
        categories: selectedCategories,
        ...brandPayload,
      }

      if (editProduct) {
        const updated = await updateWordPressProduct(editProduct.id, data)
        setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
      } else {
        const created = await createWordPressProduct(data)
        setProducts((prev) => [created, ...prev])
      }
      setShowForm(false)
    } catch (err: unknown) {
      setFormError((err as { message?: string })?.message ?? 'Error guardando producto.')
    } finally {
      setSaving(false)
    }
  }

  const toggleCategory = (id: number) => {
    setFormCategoryIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={openCreate}
            className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium"
          >
            + Nuevo producto
          </button>
          <button
            onClick={() => setShowCsvModal(true)}
            className="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium"
          >
            Importar CSV
          </button>
          <button
            onClick={handleSyncAllToDolibarr}
            disabled={syncingToDoli}
            className="px-4 py-2 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg font-medium disabled:opacity-50 flex items-center gap-1"
          >
            {syncingToDoli ? (
              <><span className="animate-spin inline-block">↻</span> Sincronizando...</>
            ) : (
              '→ Dolibarr'
            )}
          </button>
        </div>
        {selectedProductIds.size > 0 && (
          <button
            onClick={handleDeleteSelected}
            disabled={loading}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium"
          >
            Eliminar seleccionados ({selectedProductIds.size})
          </button>
        )}
        <div className="flex gap-2 flex-wrap items-center">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" clipRule="evenodd" />
              </svg>
            </div>
            <input
              type="text"
              placeholder="Buscar por nombre o SKU…"
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 w-56"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            <option value="any">Todos</option>
            <option value="publish">Publicados</option>
            <option value="draft">Borrador</option>
            <option value="private">Privados</option>
          </select>
          <button
            onClick={() => loadProducts(pagination.limit, pagination.offset, searchQuery)}
            disabled={loading}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
          >
            ↻
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {syncToDoliResult && (
        <div className="bg-green-50 border-l-4 border-green-400 p-4 rounded text-sm text-green-700 flex items-center justify-between">
          <span>
            Sync a Dolibarr completado — {syncToDoliResult.created} creados, {syncToDoliResult.updated} actualizados
            {syncToDoliResult.errors > 0 && `, ${syncToDoliResult.errors} errores`}
          </span>
          <button onClick={() => setSyncToDoliResult(null)} className="text-green-600 hover:text-green-800 font-bold ml-4">✕</button>
        </div>
      )}

      {/* Tabla */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-3 text-left text-sm font-semibold text-gray-900 w-10">
                <input
                  type="checkbox"
                  checked={products.length > 0 && products.every((p) => selectedProductIds.has(p.id))}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                  className="rounded border-gray-300 text-purple-600 shadow-sm focus:ring-purple-500"
                />
              </th>
              {['ID', 'Nombre', 'SKU', 'Marca', 'Precio', 'Stock', 'Estado', 'Acciones'].map((h) => (
                <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={9} className="px-6 py-8 text-center text-gray-500">
                  Cargando productos...
                </td>
              </tr>
            ) : products.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-8 text-center text-gray-500">
                  Sin resultados.
                </td>
              </tr>
            ) : (
              products.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-3 py-4">
                    <input
                      type="checkbox"
                      checked={selectedProductIds.has(p.id)}
                      onChange={(e) => handleSelectProduct(p.id, e.target.checked)}
                      className="rounded border-gray-300 text-purple-600 shadow-sm focus:ring-purple-500"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{p.id}</td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900 max-w-48 truncate">{p.name}</td>
                  <td className="px-6 py-4 text-sm font-mono text-gray-600">{p.sku || '—'}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{getProductBrandName(p)}</td>
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

      {/* ── Paginación avanzada ─────────────────────────────────────────────────── */}
      {(() => {
        if (pagination.total === 0) return null

        const safeLimit = pagination.limit > 0 ? pagination.limit : 1
        const currentPage = Math.floor(pagination.offset / safeLimit)
        const totalPages = Math.ceil(pagination.total / safeLimit)
        const paginationItems = getPaginationItems(currentPage + 1, totalPages)

        const PREDEFINED_PAGE_SIZES = [10, 25, 50, 100, 250, 500]
        const isCustomPageSizeActive = !PREDEFINED_PAGE_SIZES.includes(pagination.limit)

        return (
          <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-gray-600">
            {/* Selector de tamaño de página */}
            <div className="flex items-center gap-2">
              <span>Items por página:</span>
              {!showCustomPageSizeInput ? (
                <select
                  value={pagination.limit}
                  onChange={(e) => handlePageSizeChange(e.target.value)}
                  className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                >
                  {PREDEFINED_PAGE_SIZES.map((size) => (
                    <option key={size} value={size}>{size}</option>
                  ))}
                  {isCustomPageSizeActive && (
                    <option value={pagination.limit}>{pagination.limit}</option>
                  )}
                  <option value="custom">Personalizado...</option>
                </select>
              ) : (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={customPageSize}
                    onChange={(e) => setCustomPageSize(e.target.value)}
                    className="w-20 px-2 py-1 border border-gray-300 rounded"
                    min="1"
                  />
                  <button
                    onClick={handleApplyCustomPageSize}
                    className="px-2 py-1 font-medium text-purple-600 hover:text-purple-800"
                  >
                    Aplicar
                  </button>
                  <button
                    onClick={() => setShowCustomPageSizeInput(false)}
                    className="p-1 text-gray-500 hover:text-gray-700"
                    title="Cancelar"
                  >
                    &times;
                  </button>
                </div>
              )}
            </div>

            {/* Navegación de páginas */}
            {totalPages > 1 && (
              <div className="flex items-center gap-1">
                <button disabled={currentPage === 0} onClick={() => handlePageChange(0)} className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50" aria-label="Primera página">«</button>
                <button disabled={currentPage === 0} onClick={() => handlePageChange(currentPage - 1)} className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50" aria-label="Página anterior">‹</button>

                {paginationItems.map((item, index) =>
                  typeof item === 'number' ? (
                    <button
                      key={index}
                      onClick={() => handlePageChange(item - 1)}
                      aria-current={currentPage + 1 === item ? 'page' : undefined}
                      className={`px-3 py-1 border rounded ${
                        currentPage + 1 === item
                          ? 'border-purple-500 bg-purple-50 text-purple-600'
                          : 'border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {item}
                    </button>
                  ) : (
                    <span key={index} className="px-2 py-1">...</span>
                  )
                )}

                <button disabled={!pagination.has_more} onClick={() => handlePageChange(currentPage + 1)} className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50" aria-label="Página siguiente">›</button>
                <button disabled={currentPage >= totalPages - 1} onClick={() => handlePageChange(totalPages - 1)} className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50" aria-label="Última página">»</button>
              </div>
            )}

            {/* Contador total */}
            <div>
              {pagination.offset + 1} –{' '}
              {Math.min(pagination.offset + pagination.limit, pagination.total)} de{' '}
              {pagination.total}
            </div>

            {/* Input para ir a página específica */}
            <div className="flex items-center gap-1">
              <input
                type="number"
                value={goToPageInput}
                onChange={(e) => setGoToPageInput(e.target.value)}
                placeholder="Ir a pág."
                className="w-24 px-2 py-1 border border-gray-300 rounded text-sm"
                min="1"
                max={totalPages}
              />
              <button onClick={handleGoToPage} className="px-2 py-1 font-medium text-purple-600 hover:text-purple-800">
                Ir
              </button>
            </div>
          </div>
        )
      })()}

      {/* Modal importación CSV */}
      {showCsvModal && (
        <WpCsvImportModal
          onClose={() => setShowCsvModal(false)}
          onSuccess={() => { setShowCsvModal(false); loadProducts(pagination.limit, 0, searchQuery) }}
        />
      )}

      {/* Modal formulario */}
      {showForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
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
              <form onSubmit={handleSave} className="space-y-1">

                {/* ── Información básica ─────────────────────────────────── */}
                <p className={SECTION_LABEL}>Información básica</p>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Nombre *</label>
                  <input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className={INPUT_CLS}
                    placeholder="Nombre del producto"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">SKU / Referencia</label>
                    <input
                      value={formSku}
                      onChange={(e) => setFormSku(e.target.value)}
                      className={`${INPUT_CLS} font-mono`}
                      placeholder="ABC-001"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Slug URL</label>
                    <input
                      value={formSlug}
                      onChange={(e) => setFormSlug(e.target.value)}
                      className={`${INPUT_CLS} font-mono`}
                      placeholder="nombre-del-producto"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Tipo de producto</label>
                    <select
                      value={formType}
                      onChange={(e) => setFormType(e.target.value as WooProduct['type'])}
                      className={INPUT_CLS}
                    >
                      <option value="simple">Simple</option>
                      <option value="variable">Variable</option>
                      <option value="grouped">Agrupado</option>
                      <option value="external">Externo / Afiliado</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Estado</label>
                    <select
                      value={formStatus}
                      onChange={(e) => setFormStatus(e.target.value as 'publish' | 'draft')}
                      className={INPUT_CLS}
                    >
                      <option value="publish">Publicado</option>
                      <option value="draft">Borrador</option>
                    </select>
                  </div>
                </div>

                {/* ── Precios ────────────────────────────────────────────── */}
                <p className={SECTION_LABEL}>Precios</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Precio regular (€)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formPrice}
                      onChange={(e) => setFormPrice(e.target.value)}
                      onBlur={(e) => setFormPrice(toPrice(e.target.value))}
                      className={INPUT_CLS}
                      placeholder="0.00"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Precio de oferta (€)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formSalePrice}
                      onChange={(e) => setFormSalePrice(e.target.value)}
                      onBlur={(e) => setFormSalePrice(toPrice(e.target.value))}
                      className={INPUT_CLS}
                      placeholder="0.00"
                    />
                  </div>
                </div>

                {/* ── Descripciones ──────────────────────────────────────── */}
                <p className={SECTION_LABEL}>Descripción</p>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Descripción corta</label>
                  <textarea
                    rows={2}
                    value={formShortDesc}
                    onChange={(e) => setFormShortDesc(e.target.value)}
                    className={`${INPUT_CLS} resize-none`}
                    placeholder="Resumen breve del producto"
                  />
                </div>
                <div className="pt-2">
                  <label className="block text-xs font-medium text-gray-700 mb-1">Descripción larga</label>
                  <textarea
                    rows={4}
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    className={`${INPUT_CLS} resize-none`}
                    placeholder="Descripción completa del producto"
                  />
                </div>

                {/* ── Stock ──────────────────────────────────────────────── */}
                <p className={SECTION_LABEL}>Stock</p>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formManageStock}
                    onChange={(e) => setFormManageStock(e.target.checked)}
                    className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                  />
                  <span className="text-sm text-gray-700">Gestionar stock</span>
                </label>
                {formManageStock ? (
                  <div className="pt-2">
                    <label className="block text-xs font-medium text-gray-700 mb-1">Cantidad en stock</label>
                    <input
                      type="number"
                      min="0"
                      value={formStock}
                      onChange={(e) => setFormStock(e.target.value)}
                      className={INPUT_CLS}
                      placeholder="0"
                    />
                  </div>
                ) : (
                  <div className="pt-2">
                    <label className="block text-xs font-medium text-gray-700 mb-1">Estado de stock</label>
                    <select
                      value={formStockStatus}
                      onChange={(e) => setFormStockStatus(e.target.value as WooProduct['stock_status'])}
                      className={INPUT_CLS}
                    >
                      <option value="instock">En stock</option>
                      <option value="outofstock">Agotado</option>
                      <option value="onbackorder">Bajo pedido</option>
                    </select>
                  </div>
                )}

                {/* ── Datos físicos ──────────────────────────────────────── */}
                <p className={SECTION_LABEL}>Datos físicos</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Peso (kg)</label>
                    <input
                      type="number"
                      step="0.001"
                      min="0"
                      value={formWeight}
                      onChange={(e) => setFormWeight(e.target.value)}
                      className={INPUT_CLS}
                      placeholder="0.000"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3 pt-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Longitud (cm)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formLength}
                      onChange={(e) => setFormLength(e.target.value)}
                      className={INPUT_CLS}
                      placeholder="0"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Anchura (cm)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formWidth}
                      onChange={(e) => setFormWidth(e.target.value)}
                      className={INPUT_CLS}
                      placeholder="0"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Altura (cm)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formHeight}
                      onChange={(e) => setFormHeight(e.target.value)}
                      className={INPUT_CLS}
                      placeholder="0"
                    />
                  </div>
                </div>

                {/* ── Clasificación ──────────────────────────────────────── */}
                <p className={SECTION_LABEL}>Clasificación</p>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Marca</label>
                  <select
                    value={formBrandId ?? ''}
                    onChange={(e) => setFormBrandId(e.target.value ? Number(e.target.value) : null)}
                    className={INPUT_CLS}
                  >
                    <option value="">Sin marca</option>
                    {brands.map((b) => (
                      <option key={b.id} value={b.id}>{b.name}</option>
                    ))}
                  </select>
                  {brands.length === 0 && (
                    <p className="text-xs text-gray-400 mt-1">
                      No hay marcas configuradas en WooCommerce.
                    </p>
                  )}
                </div>
                {(categoryTree.length > 0 || categories.length > 0) && (
                  <div className="pt-2">
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      Categorías
                      {formCategoryIds.length > 0 && (
                        <span className="ml-2 text-purple-600">({formCategoryIds.length} seleccionadas)</span>
                      )}
                    </label>
                    <div className="border border-gray-300 rounded-lg max-h-48 overflow-y-auto divide-y divide-gray-100">
                      {(categoryTree.length > 0 ? categoryTree : categories.map((c) => ({ ...c, level: 0 }))).map((c) => (
                        <label
                          key={c.id}
                          className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm"
                          style={{ paddingLeft: `${12 + c.level * 16}px` }}
                        >
                          <input
                            type="checkbox"
                            checked={formCategoryIds.includes(c.id)}
                            onChange={() => toggleCategory(c.id)}
                            className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500 flex-shrink-0"
                          />
                          {c.level > 0 && (
                            <span className="text-gray-400 flex-shrink-0">└</span>
                          )}
                          <span className="text-gray-800">{c.name}</span>
                          {c.count !== undefined && (
                            <span className="ml-auto text-xs text-gray-400 flex-shrink-0">{c.count}</span>
                          )}
                        </label>
                      ))}
                    </div>
                  </div>
                )}

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

// ── CSV Import Modal ──────────────────────────────────────────────────────────

type CsvStep = 'upload' | 'mapping' | 'importing' | 'results'

interface WpCsvImportModalProps {
  onClose: () => void
  onSuccess: () => void
}

/**
 * Modal multi-paso para importación masiva de productos WooCommerce desde CSV.
 *
 * Paso 1 — Upload: usuario selecciona el CSV.
 * Paso 2 — Mapping: mapea columnas CSV a campos WooCommerce + opciones de marca/categoría.
 * Paso 3 — Importando: progreso en tiempo real via polling.
 * Paso 4 — Results: resumen creados/actualizados/omitidos/errores.
 *
 * @author Carlos Vico | BenjaminDTS
 */
function WpCsvImportModal({ onClose, onSuccess }: WpCsvImportModalProps): React.ReactElement {
  const [step, setStep] = useState<CsvStep>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<{ headers: string[]; preview: Record<string, string>[]; total_rows: number } | null>(null)
  const [wcFields, setWcFields] = useState<WcImportField[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [overwrite, setOverwrite] = useState(false)
  const [brandColumn, setBrandColumn] = useState('')
  const [categoryColumn, setCategoryColumn] = useState('')
  const [subcategoryColumn, setSubcategoryColumn] = useState('')
  const [result, setResult] = useState<WpImportTask['results'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [importProgress, setImportProgress] = useState<{ processed: number; total: number }>({ processed: 0, total: 0 })
  const [importMessage, setImportMessage] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    getWordPressCsvFields().then(setWcFields).catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const fieldOptions = [
    { value: '', label: '— Ignorar columna —' },
    ...wcFields.map((f) => ({ value: f.key, label: f.label })),
  ]

  const processFile = async (f: File) => {
    setFile(f); setError(null); setLoading(true)
    try {
      const data = await previewWordPressCsv(f)
      setPreview(data)
      const initial: Record<string, string> = {}
      data.headers.forEach((h) => { initial[h] = '' })
      setMapping(initial)
      setStep('mapping')
    } catch (err) {
      setError((err as { message?: string }).message ?? 'Error analizando CSV')
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    const activeMapping = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v !== ''))
    if (!Object.values(activeMapping).includes('name')) {
      setError("Debes asignar al menos una columna al campo 'Nombre del producto'.")
      return
    }
    if (!file) return
    setError(null)
    setImportProgress({ processed: 0, total: 0 })
    setImportMessage('')
    setStep('importing')

    try {
      const task = await importWordPressCsv(file, activeMapping, overwrite, brandColumn || undefined, categoryColumn || undefined, subcategoryColumn || undefined)

      pollRef.current = setInterval(async () => {
        try {
          const status = await getWordPressImportStatus(task.task_id)
          setImportProgress(status.progress)
          setImportMessage(status.message)

          if (status.status === 'completed' && status.results) {
            clearInterval(pollRef.current!); pollRef.current = null
            setResult(status.results)
            setStep('results')
            if ((status.results.created ?? 0) > 0 || (status.results.updated ?? 0) > 0) onSuccess()
          } else if (status.status === 'failed') {
            clearInterval(pollRef.current!); pollRef.current = null
            setError(status.message)
            setStep('mapping')
          }
        } catch {
          // Network blip — mantener polling
        }
      }, 2000)

    } catch (err) {
      setError((err as { message?: string }).message ?? 'Error iniciando importación')
      setStep('mapping')
    }
  }

  const nameMapped = Object.values(mapping).includes('name')

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Importar productos desde CSV</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {step === 'upload' && 'Paso 1 de 3 — Seleccionar archivo'}
              {step === 'mapping' && `Paso 2 de 3 — Mapear columnas (${preview?.total_rows ?? 0} filas)`}
              {step === 'importing' && 'Paso 3 de 3 — Importando...'}
              {step === 'results' && 'Paso 3 de 3 — Resultado'}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-5">

          {/* Step 1: Upload */}
          {step === 'upload' && (
            <div className="space-y-4">
              <div
                onClick={() => fileInputRef.current?.click()}
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) processFile(f) }}
                onDragOver={(e) => e.preventDefault()}
                className="border-2 border-dashed border-gray-300 rounded-lg p-10 text-center cursor-pointer hover:border-purple-400 hover:bg-purple-50 transition-colors"
              >
                <input ref={fileInputRef} type="file" accept=".csv,.tsv,.txt" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) processFile(f) }} />
                <p className="text-4xl mb-3">📄</p>
                {file ? (
                  <p className="text-sm font-medium text-gray-800">{file.name}</p>
                ) : (
                  <>
                    <p className="text-sm font-medium text-gray-700">Arrastra tu CSV aquí o haz clic para seleccionar</p>
                    <p className="text-xs text-gray-400 mt-1">UTF-8 o Latin-1 · Máximo 10 MB</p>
                  </>
                )}
              </div>
              {file && <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600"><span className="font-medium">{file.name}</span>{' · '}{(file.size / 1024).toFixed(1)} KB</div>}
              {loading && <p className="text-sm text-gray-500 text-center">Analizando CSV...</p>}
              {error && <div className="bg-red-50 border-l-4 border-red-400 p-3 rounded text-sm text-red-700">{error}</div>}
            </div>
          )}

          {/* Step 2: Mapping */}
          {step === 'mapping' && preview && (
            <div className="space-y-5">
              {/* Overwrite toggle */}
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-gray-300 text-purple-600 focus:ring-purple-500" />
                  <div>
                    <p className="text-sm font-medium text-purple-900">Actualizar productos existentes</p>
                    <p className="text-xs text-purple-700 mt-0.5">Si está activo, los productos con el mismo <strong>SKU</strong> se actualizarán. Si está inactivo, se omiten.</p>
                  </div>
                </label>
              </div>

              {/* Preview table */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Previsualización — primeras {preview.preview.length} filas</p>
                <div className="overflow-x-auto rounded border border-gray-200 text-xs">
                  <table className="min-w-full">
                    <thead className="bg-gray-50">
                      <tr>{preview.headers.map((h) => <th key={h} className="px-3 py-2 text-left font-medium text-gray-700 whitespace-nowrap">{h}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {preview.preview.map((row, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          {preview.headers.map((h) => <td key={h} className="px-3 py-1.5 text-gray-600 max-w-32 truncate">{row[h] ?? ''}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Mapping */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Mapeo de columnas <span className="text-red-500">*</span> = obligatorio</p>
                <div className="space-y-2">
                  {preview.headers.map((h) => (
                    <div key={h} className="grid grid-cols-2 gap-3 items-center">
                      <span className="text-sm font-mono text-gray-700 truncate" title={h}>{h}</span>
                      <select
                        value={mapping[h] ?? ''}
                        onChange={(e) => setMapping((prev) => ({ ...prev, [h]: e.target.value }))}
                        className="px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      >
                        {fieldOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
                {!nameMapped && <p className="text-xs text-red-500 mt-2">⚠ Debes mapear al menos una columna a "Nombre del producto".</p>}
              </div>

              {/* Optional columns */}
              <div className="border border-purple-200 bg-purple-50 rounded-lg p-4 space-y-3">
                <p className="text-xs font-semibold text-purple-800 uppercase tracking-wide">Columnas especiales (opcionales)</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-purple-800 mb-1">Columna de marca</label>
                    <select value={brandColumn} onChange={(e) => setBrandColumn(e.target.value)} className="w-full px-2 py-1.5 border border-purple-300 rounded text-sm bg-white focus:ring-2 focus:ring-purple-400">
                      <option value="">— Sin marca —</option>
                      {preview.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                    <p className="text-xs text-purple-600 mt-1">Se crea la marca si no existe.</p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-purple-800 mb-1">Columna de categoría</label>
                    <select value={categoryColumn} onChange={(e) => setCategoryColumn(e.target.value)} className="w-full px-2 py-1.5 border border-purple-300 rounded text-sm bg-white focus:ring-2 focus:ring-purple-400">
                      <option value="">— Sin categoría —</option>
                      {preview.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                    <p className="text-xs text-purple-600 mt-1">Se crea la categoría si no existe.</p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-purple-800 mb-1">Columna de subcategoría</label>
                    <select
                      value={subcategoryColumn}
                      onChange={(e) => setSubcategoryColumn(e.target.value)}
                      disabled={!categoryColumn}
                      className="w-full px-2 py-1.5 border border-purple-300 rounded text-sm bg-white focus:ring-2 focus:ring-purple-400 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="">— Sin subcategoría —</option>
                      {preview.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                    <p className="text-xs text-purple-600 mt-1">
                      {categoryColumn ? 'Se crea bajo la categoría padre.' : 'Requiere categoría padre.'}
                    </p>
                  </div>
                </div>
              </div>

              {error && <div className="bg-red-50 border-l-4 border-red-400 p-3 rounded text-sm text-red-700">{error}</div>}
            </div>
          )}

          {/* Step 3: Importing */}
          {step === 'importing' && (
            <div className="space-y-6 py-8">
              <div className="text-center">
                <div className="inline-block w-10 h-10 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mb-4" />
                <p className="text-sm font-medium text-gray-800">{importMessage || 'Iniciando importación...'}</p>
                {importProgress.total > 0 && (
                  <p className="text-xs text-gray-500 mt-1">{importProgress.processed} / {importProgress.total} productos</p>
                )}
              </div>
              {importProgress.total > 0 && (
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-purple-600 h-2 rounded-full transition-all"
                    style={{ width: `${Math.round((importProgress.processed / importProgress.total) * 100)}%` }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Step 4: Results */}
          {step === 'results' && result && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Creados', value: result.created, cls: 'bg-green-50 text-green-800 border-green-200' },
                  { label: 'Actualizados', value: result.updated, cls: 'bg-blue-50 text-blue-800 border-blue-200' },
                  { label: 'Omitidos', value: result.skipped, cls: 'bg-gray-50 text-gray-800 border-gray-200' },
                  { label: 'Errores', value: result.errors, cls: 'bg-red-50 text-red-800 border-red-200' },
                ].map(({ label, value, cls }) => (
                  <div key={label} className={`border rounded-lg p-3 text-center ${cls}`}>
                    <p className="text-2xl font-bold">{value}</p>
                    <p className="text-xs font-medium mt-1">{label}</p>
                  </div>
                ))}
              </div>
              {result.errors > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Filas con error</p>
                  <div className="overflow-y-auto max-h-48 rounded border border-red-200 divide-y divide-red-100 text-xs">
                    {result.results
                      .filter((r) => r.action === 'error')
                      .map((r) => (
                        <div key={r.row} className="px-3 py-2 text-red-700">
                          <span className="font-mono font-medium">Fila {r.row}</span>
                          {r.sku && <span className="ml-2 text-red-500">({r.sku})</span>}
                          <span className="ml-2">— {r.error}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
              {(() => {
                const withCatError = result.results.filter((r) => r.category_error)
                const withCat = result.results.filter((r) => r.categories_in_payload && !r.category_error)
                const noCat = result.results.filter((r) => !r.categories_in_payload && !r.category_error)
                return (
                  <div className="border border-gray-200 rounded-lg p-3 space-y-2 text-xs">
                    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Diagnóstico de categorías</p>
                    <div className="flex gap-4">
                      <span className="text-green-700">✓ Con categoría: {withCat.length}</span>
                      <span className="text-orange-700">⚠ Error categoría: {withCatError.length}</span>
                      <span className="text-gray-500">– Sin col. categoría: {noCat.length}</span>
                    </div>
                    {withCatError.length > 0 && (
                      <div className="overflow-y-auto max-h-32 rounded border border-orange-200 divide-y divide-orange-100">
                        {withCatError.map((r) => (
                          <div key={r.row} className="px-3 py-1.5 text-orange-700">
                            <span className="font-mono font-medium">Fila {r.row}</span>
                            {r.sku && <span className="ml-2 text-orange-500">({r.sku})</span>}
                            <span className="ml-2">— {r.category_error}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })()}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex gap-3 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">
            {step === 'results' ? 'Cerrar' : 'Cancelar'}
          </button>
          {step === 'mapping' && (
            <button
              onClick={handleImport}
              disabled={!nameMapped}
              className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium"
            >
              Importar {preview?.total_rows ?? ''} productos
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
