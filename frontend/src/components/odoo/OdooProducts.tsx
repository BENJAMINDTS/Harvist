/**
 * Panel de productos de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooProducts, deleteOdooProduct, updateOdooProduct, createOdooProduct, listOdooCategories } from '@/api/client'
import type { OdooProduct, OdooCategory } from '@/types/odoo'
import OdooCsvImport from './OdooCsvImport'
import OdooProductProperties from './OdooProductProperties'

const formatField = (v: [number, string] | false | string | undefined) => {
  if (!v) return '—'
  if (Array.isArray(v)) return v[1]
  return String(v)
}

export default function OdooProducts() {
  const [products, setProducts] = useState<OdooProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [editingProduct, setEditingProduct] = useState<OdooProduct | null>(null)
  const [creatingProduct, setCreatingProduct] = useState(false)
  const [importingCsv, setImportingCsv] = useState(false)
  const [pagination, setPagination] = useState({
    limit: 10,
    offset: 0,
    total: 0,
    has_more: false,
  })

  const load = async (limit = 10, offset = 0, q = search) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listOdooProducts(limit, offset, q)
      setProducts(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando productos')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este producto de Odoo?')) return
    try {
      await deleteOdooProduct(id)
      load(pagination.limit, pagination.offset)
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando producto')
    }
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
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          Buscar
        </button>
        <button
          onClick={() => setCreatingProduct(true)}
          className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700"
        >
          + Nuevo producto
        </button>
        <button
          onClick={() => setImportingCsv(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700"
        >
          Importar CSV
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Referencia</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Nombre</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Categoría</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Precio</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Stock</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Estado</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Cargando productos...</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Sin productos</td></tr>
            ) : products.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm text-gray-900">{formatField(p.default_code)}</td>
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{p.name}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(p.categ_id)}</td>
                <td className="px-6 py-4 text-sm text-gray-900">€{p.list_price.toFixed(2)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{p.qty_available.toFixed(0)}</td>
                <td className="px-6 py-4 text-sm">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${p.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                    {p.active ? 'Activo' : 'Inactivo'}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm">
                  <div className="flex gap-3">
                    <button
                      onClick={() => setEditingProduct(p)}
                      className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="text-red-600 hover:text-red-800 text-xs font-medium"
                    >
                      Eliminar
                    </button>
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

      {editingProduct && (
        <ProductModal
          product={editingProduct}
          onClose={() => setEditingProduct(null)}
          onSuccess={() => {
            setEditingProduct(null)
            load(pagination.limit, pagination.offset)
          }}
        />
      )}

      {creatingProduct && (
        <ProductModal
          product={null}
          onClose={() => setCreatingProduct(false)}
          onSuccess={() => {
            setCreatingProduct(false)
            load(pagination.limit, pagination.offset)
          }}
        />
      )}

      {importingCsv && (
        <OdooCsvImport
          onClose={() => setImportingCsv(false)}
          onSuccess={() => load(pagination.limit, pagination.offset)}
        />
      )}
    </div>
  )
}

// ── Create / Edit modal ───────────────────────────────────────────────────

interface ProductModalProps {
  product: OdooProduct | null
  onClose: () => void
  onSuccess: () => void
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'
const SECTION_CLS = 'border border-gray-100 rounded-lg p-4 space-y-3'
const SECTION_TITLE_CLS = 'text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3'

type FormValues = Record<string, string>

function initValues(p: OdooProduct | null): FormValues {
  const str = (v: string | false | number | boolean | null | undefined) =>
    v == null || v === false ? '' : String(v)
  if (!p) {
    return {
      name: '',
      default_code: '',
      active: '1',
      priority: '0',
      detailed_type: 'product',
      tracking: 'none',
      categ_id: '',
      list_price: '0',
      compare_list_price: '',
      standard_price: '0',
      weight: '',
      volume: '',
      sale_delay: '',
      hs_code: '',
      sale_ok: '1',
      invoice_policy: 'order',
      description_sale: '',
      purchase_ok: '1',
      purchase_method: 'purchase',
      description_purchase: '',
      is_published: '0',
      available_in_pos: '0',
      website_meta_title: '',
      website_meta_description: '',
      website_meta_keywords: '',
      description: '',
    }
  }
  return {
    name: p.name,
    default_code: str(p.default_code),
    active: p.active ? '1' : '0',
    priority: str(p.priority),
    detailed_type: p.detailed_type ?? p.type ?? 'product',
    tracking: p.tracking ?? 'none',
    categ_id: p.categ_id ? String(p.categ_id[0]) : '',
    list_price: str(p.list_price),
    compare_list_price: str(p.compare_list_price),
    standard_price: str(p.standard_price),
    weight: str(p.weight),
    volume: str(p.volume),
    sale_delay: str(p.sale_delay),
    hs_code: str(p.hs_code),
    sale_ok: p.sale_ok ? '1' : '0',
    invoice_policy: str(p.invoice_policy) || 'order',
    description_sale: str(p.description_sale),
    purchase_ok: p.purchase_ok ? '1' : '0',
    purchase_method: str(p.purchase_method) || 'purchase',
    description_purchase: str(p.description_purchase),
    is_published: p.is_published ? '1' : '0',
    available_in_pos: p.available_in_pos ? '1' : '0',
    website_meta_title: str(p.website_meta_title),
    website_meta_description: str(p.website_meta_description),
    website_meta_keywords: str(p.website_meta_keywords),
    description: str(p.description),
  }
}

function buildPayload(values: FormValues): Partial<OdooProduct> {
  const payload: Record<string, unknown> = {}

  payload.name = values.name.trim()
  payload.default_code = values.default_code.trim() || false
  payload.active = values.active === '1'
  payload.priority = values.priority || '0'
  payload.detailed_type = values.detailed_type
  payload.tracking = values.tracking
  if (values.categ_id) payload.categ_id = parseInt(values.categ_id, 10)
  payload.list_price = parseFloat(values.list_price) || 0
  if (values.compare_list_price) payload.compare_list_price = parseFloat(values.compare_list_price)
  if (values.standard_price) payload.standard_price = parseFloat(values.standard_price)
  if (values.weight) payload.weight = parseFloat(values.weight)
  if (values.volume) payload.volume = parseFloat(values.volume)
  if (values.sale_delay) payload.sale_delay = parseInt(values.sale_delay, 10)
  payload.hs_code = values.hs_code.trim() || false
  payload.sale_ok = values.sale_ok === '1'
  payload.invoice_policy = values.invoice_policy || false
  payload.description_sale = values.description_sale.trim() || false
  payload.purchase_ok = values.purchase_ok === '1'
  payload.purchase_method = values.purchase_method || false
  payload.description_purchase = values.description_purchase.trim() || false
  payload.is_published = values.is_published === '1'
  payload.available_in_pos = values.available_in_pos === '1'
  payload.website_meta_title = values.website_meta_title.trim() || false
  payload.website_meta_description = values.website_meta_description.trim() || false
  payload.website_meta_keywords = values.website_meta_keywords.trim() || false
  payload.description = values.description.trim() || false

  return payload as Partial<OdooProduct>
}

function ProductModal({ product, onClose, onSuccess }: ProductModalProps) {
  const isCreate = product === null
  const [values, setValues] = useState<FormValues>(() => initValues(product))
  const [categories, setCategories] = useState<OdooCategory[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listOdooCategories(200, 0)
      .then((r) => setCategories(Array.isArray(r?.items) ? r.items : []))
      .catch(() => {})
  }, [])

  const set = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    if (!values.name.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    if (isCreate && !values.default_code.trim()) {
      setError('La referencia interna es obligatoria al crear un producto.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      if (isCreate) {
        await createOdooProduct(buildPayload(values))
      } else {
        await updateOdooProduct(product.id, buildPayload(values))
      }
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? (isCreate ? 'Error creando producto' : 'Error actualizando producto'))
    } finally {
      setSubmitting(false)
    }
  }

  const uomLabel = product?.uom_id ? `${product.uom_id[1]} (ID ${product.uom_id[0]})` : '—'
  const uomPoLabel = product?.uom_po_id ? `${product.uom_po_id[1]} (ID ${product.uom_po_id[0]})` : '—'

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <h3 className="text-lg font-semibold text-gray-900">
            {isCreate ? 'Nuevo producto' : `Editar producto — ${product.name}`}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">

          {/* Información general */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Información general</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className={LABEL_CLS}>Nombre <span className="text-red-500">*</span></label>
                <input type="text" value={values.name} onChange={(e) => set('name', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>
                  Referencia interna {isCreate && <span className="text-red-500">*</span>}
                </label>
                <input type="text" value={values.default_code} onChange={(e) => set('default_code', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Activo</label>
                <select value={values.active} onChange={(e) => set('active', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Sí</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Favorito</label>
                <select value={values.priority} onChange={(e) => set('priority', e.target.value)} className={INPUT_CLS}>
                  <option value="0">Normal</option>
                  <option value="1">Favorito</option>
                </select>
              </div>
            </div>
          </div>

          {/* Tipo y categoría */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Tipo y categoría</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Tipo de producto</label>
                <select value={values.detailed_type} onChange={(e) => set('detailed_type', e.target.value)} className={INPUT_CLS}>
                  <option value="consu">Consumible</option>
                  <option value="service">Servicio</option>
                  <option value="product">Almacenable</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Seguimiento</label>
                <select value={values.tracking} onChange={(e) => set('tracking', e.target.value)} className={INPUT_CLS}>
                  <option value="none">Sin seguimiento</option>
                  <option value="lot">Por lote</option>
                  <option value="serial">Por número de serie</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Categoría</label>
                <select value={values.categ_id} onChange={(e) => set('categ_id', e.target.value)} className={INPUT_CLS}>
                  <option value="">— Sin cambio —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={String(c.id)}>{c.complete_name || c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>HS Code</label>
                <input type="text" value={values.hs_code} onChange={(e) => set('hs_code', e.target.value)} placeholder="p.ej. 8471300000" className={INPUT_CLS} />
              </div>
              {!isCreate && (
                <>
                  <div>
                    <label className={LABEL_CLS}>Unidad de medida</label>
                    <input type="text" value={uomLabel} disabled className={`${INPUT_CLS} bg-gray-50 text-gray-500`} />
                  </div>
                  <div>
                    <label className={LABEL_CLS}>UdM de compra</label>
                    <input type="text" value={uomPoLabel} disabled className={`${INPUT_CLS} bg-gray-50 text-gray-500`} />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Precios */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Precios</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className={LABEL_CLS}>Precio de venta (€)</label>
                <input type="number" step="0.01" min="0" value={values.list_price} onChange={(e) => set('list_price', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Precio comparativo (€)</label>
                <input type="number" step="0.01" min="0" value={values.compare_list_price} onChange={(e) => set('compare_list_price', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Coste (€)</label>
                <input type="number" step="0.01" min="0" value={values.standard_price} onChange={(e) => set('standard_price', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          {/* Medidas y logística */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Medidas y logística</p>
            <div className="grid grid-cols-4 gap-3">
              <div>
                <label className={LABEL_CLS}>Peso (kg)</label>
                <input type="number" step="0.001" min="0" value={values.weight} onChange={(e) => set('weight', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Volumen (m³)</label>
                <input type="number" step="0.001" min="0" value={values.volume} onChange={(e) => set('volume', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Plazo cliente (días)</label>
                <input type="number" step="1" min="0" value={values.sale_delay} onChange={(e) => set('sale_delay', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          {/* Ventas */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Ventas</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Se puede vender</label>
                <select value={values.sale_ok} onChange={(e) => set('sale_ok', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Sí</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Política de facturación</label>
                <select value={values.invoice_policy} onChange={(e) => set('invoice_policy', e.target.value)} className={INPUT_CLS}>
                  <option value="order">Cantidades pedidas</option>
                  <option value="delivery">Cantidades entregadas</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>Descripción de ventas</label>
                <textarea rows={3} value={values.description_sale} onChange={(e) => set('description_sale', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          {/* Compras */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Compras</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Se puede comprar</label>
                <select value={values.purchase_ok} onChange={(e) => set('purchase_ok', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Sí</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Política de control</label>
                <select value={values.purchase_method} onChange={(e) => set('purchase_method', e.target.value)} className={INPUT_CLS}>
                  <option value="purchase">Cantidad pedida</option>
                  <option value="receive">Cantidades recibidas</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>Descripción de compras</label>
                <textarea rows={3} value={values.description_purchase} onChange={(e) => set('description_purchase', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          {/* eCommerce */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>eCommerce</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Publicado en web</label>
                <select value={values.is_published} onChange={(e) => set('is_published', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Sí</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Disponible en POS</label>
                <select value={values.available_in_pos} onChange={(e) => set('available_in_pos', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Sí</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>Meta título (SEO)</label>
                <input type="text" value={values.website_meta_title} onChange={(e) => set('website_meta_title', e.target.value)} className={INPUT_CLS} />
              </div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>Meta descripción (SEO)</label>
                <textarea rows={2} value={values.website_meta_description} onChange={(e) => set('website_meta_description', e.target.value)} className={INPUT_CLS} />
              </div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>Meta palabras clave</label>
                <input type="text" value={values.website_meta_keywords} onChange={(e) => set('website_meta_keywords', e.target.value)} placeholder="palabra1, palabra2, ..." className={INPUT_CLS} />
              </div>
            </div>
          </div>

          {/* Descripción interna */}
          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Descripción interna</p>
            <textarea rows={4} value={values.description} onChange={(e) => set('description', e.target.value)} className={INPUT_CLS} />
          </div>

          {/* Campos extra (Properties) — solo en edición */}
          {!isCreate && (
            <div className={SECTION_CLS}>
              <p className={SECTION_TITLE_CLS}>Campos extra</p>
              <OdooProductProperties
                productId={product!.id}
                categoryId={Array.isArray(product!.categ_id) ? product!.categ_id[0] : false}
              />
            </div>
          )}

        </div>

        <div className="px-6 py-4 border-t border-gray-200 space-y-3 flex-shrink-0">
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Guardando...' : isCreate ? 'Crear producto' : 'Guardar cambios'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
