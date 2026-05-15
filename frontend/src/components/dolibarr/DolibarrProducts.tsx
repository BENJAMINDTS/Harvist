/**
 * Módulo de gestión de productos de Dolibarr.
 * El formulario de creación/edición es completamente dinámico:
 * obtiene el schema de campos desde el endpoint /products/fields,
 * que combina campos estándar con los extra fields configurados en esa instancia.
 *
 * @author BenjaminDTS
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  listDolibarrProducts,
  deleteDolibarrProduct,
  syncDolibarrFromJob,
  createDolibarrProduct,
  updateDolibarrProduct,
  getDolibarrProductFields,
  previewDolibarrCsv,
  importDolibarrCsv,
  getDolibarrImportStatus,
  deleteDolibarrProducts,
  listDolibarrCategories,
  listDolibarrBrands,
} from '@/api/client'
import {
  type DolibarrProduct,
  type DolibarrFieldSchema,
  type DolibarrFieldType,
  type DolibarrFieldOption,
  type CsvImportPreview,
  type DolibarrImportTask,
  type DolibarrCategory,
} from '@/types/dolibarr'

// ─── Helper de paginación ─────────────────────────────────────────────────────

const getPaginationItems = (currentPage: number, totalPages: number): (number | string)[] => {
  // currentPage es 1-based. delta define cuántas páginas adyacentes mostrar.
  const delta = 2
  const left = currentPage - delta // Páginas a la izquierda de la actual
  const right = currentPage + delta + 1 // Páginas a la derecha de la actual
  const range: number[] = []
  const rangeWithDots: (number | string)[] = []
  let l: number | undefined

  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= left && i < right)) {
      range.push(i)
    }
  }

  for (const i of range) {
    if (l) {
      if (i - l === 2) {
        rangeWithDots.push(l + 1)
      } else if (i - l !== 1) {
        rangeWithDots.push('...')
      }
    }
    rangeWithDots.push(i)
    l = i
  }

  return rangeWithDots
}

export default function DolibarrProducts() {
  const [products, setProducts] = useState<DolibarrProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pagination, setPagination] = useState({
    limit: 10,
    offset: 0,
    total: 0,
    has_more: false,
  })
  const [showSyncModal, setShowSyncModal] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showCsvImportModal, setShowCsvImportModal] = useState(false)
  const [editingProduct, setEditingProduct] = useState<DolibarrProduct | null>(null)
  const [customPageSize, setCustomPageSize] = useState('')
  const [showCustomPageSizeInput, setShowCustomPageSizeInput] = useState(false)
  const [goToPageInput, setGoToPageInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedProductIds, setSelectedProductIds] = useState<Set<number>>(new Set())
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  
  const loadProducts = useCallback(async (limit = 10, offset = 0, query = '') => {
    try {
      setLoading(true)
      const data = await listDolibarrProducts(limit, offset, query)
      setProducts(data.items)
      setPagination({
        limit: data.limit,
        offset: data.offset,
        total: data.total,
        has_more: data.has_more,
      })
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando productos')
    } finally {
      setLoading(false)
    }
  }, [])
  
  useEffect(() => {
    loadProducts()
  }, [loadProducts])

  const handleDeleteSingle = useCallback(async (id: number): Promise<void> => {
    if (!confirm('¿Eliminar este producto?')) return
    try {
      await deleteDolibarrProduct(id)
      // Recargar con la paginación y búsqueda actual
      loadProducts(pagination.limit, pagination.offset, searchQuery)
      setSelectedProductIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando producto')
    }
  }, [loadProducts, pagination.limit, pagination.offset, searchQuery])

  // ── Lógica de paginación ───────────────────────────────────────────────────

  const handlePageSizeChange = (newSize: number | string): void => {
    if (newSize === 'custom') {
      setShowCustomPageSizeInput(true)
      setCustomPageSize(String(pagination.limit))
    } else {
      setShowCustomPageSizeInput(false)
      const size = Number(newSize)
      if (size > 0) {
        loadProducts(size, 0, searchQuery)
      }
    }
  }

  const handleApplyCustomPageSize = (): void => {
    const size = parseInt(customPageSize, 10)
    if (size > 0) {
      setShowCustomPageSizeInput(false)
      loadProducts(size, 0, searchQuery)
    }
  }

  const handlePageChange = (pageNumber: number): void => {
    // pageNumber es 0-indexed
    const newOffset = pageNumber * pagination.limit
    if (newOffset >= 0 && newOffset < pagination.total || pageNumber === 0 && pagination.total === 0) {
      loadProducts(pagination.limit, newOffset, searchQuery)
      setGoToPageInput('') // Limpiar el input después de navegar
    }
  }

  const handleGoToPage = useCallback(() => {
    const pageNum = parseInt(goToPageInput, 10)
    const totalPages = Math.ceil(pagination.total / pagination.limit)
    if (!isNaN(pageNum) && pageNum >= 1 && pageNum <= totalPages) {
      handlePageChange(pageNum - 1) // Convertir a 0-indexed
    } else {
      alert(`Por favor, introduce un número de página válido entre 1 y ${totalPages}.`)
    }
  }, [goToPageInput, pagination.limit, pagination.total, handlePageChange]);

  const handleSelectProduct = useCallback((productId: number, isSelected: boolean) => {
    setSelectedProductIds((prev: Set<number>) => {
      const newSet = new Set(prev);
      if (isSelected) {
        newSet.add(productId);
      } else {
        newSet.delete(productId);
      }
      return newSet;
    });
  }, []);

  const handleDeleteSelected = useCallback(async (): Promise<void> => {
    if (selectedProductIds.size === 0) return;
    if (!confirm(`¿Eliminar ${selectedProductIds.size} productos seleccionados?`)) return;

    setLoading(true);
    setError(null);
    try {
      await deleteDolibarrProducts(Array.from(selectedProductIds));
      setSelectedProductIds(new Set()); // Limpiar todas las selecciones
      loadProducts(pagination.limit, pagination.offset, searchQuery); // Recargar la página actual
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando productos seleccionados');
    } finally {
      setLoading(false);
    }
  }, [loadProducts, pagination.limit, pagination.offset, searchQuery, selectedProductIds]);

  const handleSelectAllProducts = useCallback((isChecked: boolean) => {
    setSelectedProductIds(prev => {
      const newSet = new Set(prev);
      if (isChecked) {
        products.forEach(p => newSet.add(p.id));
      } else {
        products.forEach(p => newSet.delete(p.id));
      }
      return newSet;
    });
  }, [products]);

  const handleSearchChange = (query: string) => {
    setSearchQuery(query)
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    searchTimeoutRef.current = setTimeout(() => {
      // Al buscar, siempre volvemos a la primera página
      loadProducts(pagination.limit, 0, query)
    }, 300)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-2">
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
          >
            + Nuevo producto
          </button>
          <button
            onClick={() => setShowSyncModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            ↓ Sincronizar desde job
          </button>
          <button
            onClick={() => setShowCsvImportModal(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium"
          >
            Importar CSV
          </button>
        </div>
        {/* Botón de eliminar seleccionados */}
        {selectedProductIds.size > 0 && (
          <button
            onClick={handleDeleteSelected}
            disabled={loading}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium"
          >
            Eliminar seleccionados ({selectedProductIds.size})
          </button>
        )}
        <div className="relative sm:w-auto w-full">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <svg className="h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" clipRule="evenodd" />
            </svg>
          </div>
          <input
            type="text"
            placeholder="Buscar por nombre o referencia..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full sm:w-64 pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          />
        </div>
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
              {/* Checkbox para seleccionar todos */}
              <th className="px-3 py-3 text-left text-sm font-semibold text-gray-900 w-10">
                <input
                  type="checkbox"
                  checked={products.length > 0 && products.every(p => selectedProductIds.has(p.id))}
                  onChange={(e) => handleSelectAllProducts(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 shadow-sm focus:ring-blue-500"
                />
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Ref</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Nombre</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Precio</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Tipo</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Estado</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                  Cargando productos...
                </td>
              </tr>
            ) : products.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                  Sin productos
                </td>
              </tr>
            ) : (
              products.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  {/* Checkbox individual */}
                  <td className="px-3 py-4 align-top">
                    <input
                      type="checkbox"
                      checked={selectedProductIds.has(p.id)}
                      onChange={(e) => handleSelectProduct(p.id, e.target.checked)}
                      className="rounded border-gray-300 text-blue-600 shadow-sm focus:ring-blue-500"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">{p.ref}</td>
                  <td className="px-6 py-4 text-sm text-gray-900">{p.label}</td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    €{Number(p.price).toFixed(2)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {p.type === 0 ? 'Producto' : 'Servicio'}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        Number(p.status) === 1
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {p.status === 1 ? 'Activo' : 'Inactivo'}
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
                        onClick={() => handleDeleteSingle(p.id)}
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

        const currentPage = Math.floor(pagination.offset / pagination.limit)
        const totalPages = Math.ceil(pagination.total / pagination.limit)
        const paginationItems = getPaginationItems(currentPage + 1, totalPages)

        const PREDEFINED_PAGE_SIZES = [10, 25, 50, 100]
        const isCustomPageSizeActive = !PREDEFINED_PAGE_SIZES.includes(pagination.limit)

        return (
          <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-gray-600">
            {/* Selector de tamaño de página */}
            <div className="flex items-center gap-2">
              <span>Items por página:</span>
              {!showCustomPageSizeInput ? (
                <select
                  value={pagination.limit} // El valor ahora siempre coincidirá con una opción
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
                    className="px-2 py-1 font-medium text-blue-600 hover:text-blue-800"
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
                          ? 'border-blue-500 bg-blue-50 text-blue-600'
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
              <button onClick={handleGoToPage} className="px-2 py-1 font-medium text-blue-600 hover:text-blue-800">
                Ir
              </button>
            </div>
          </div>
        )
      })()}

      {showCreateModal && (
        <CreateProductModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false)
            loadProducts(pagination.limit, pagination.offset, searchQuery)
          }}
        />
      )}

      {editingProduct && (
        <EditProductModal
          product={editingProduct}
          onClose={() => setEditingProduct(null)}
          onSuccess={() => {
            setEditingProduct(null)
            loadProducts(pagination.limit, pagination.offset, searchQuery)
          }}
        />
      )}

      {showSyncModal && (
        <SyncFromJobModal
          onClose={() => setShowSyncModal(false)}
          onSuccess={() => {
            setShowSyncModal(false)
            loadProducts(pagination.limit, pagination.offset, searchQuery)
          }}
        />
      )}

      {showCsvImportModal && (
        <CsvImportModal
          onClose={() => setShowCsvImportModal(false)}
          onSuccess={() => {
            setShowCsvImportModal(false)
            loadProducts(pagination.limit, pagination.offset, searchQuery)
          }}
        />
      )}
    </div>
  )
}

// ── Dynamic form helpers ─────────────────────────────────────────────────

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'
const SECTION_CLS = 'border border-gray-100 rounded-lg p-4 space-y-3'
const SECTION_TITLE_CLS = 'text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3'

function renderFieldInput(
  field: DolibarrFieldSchema,
  value: string,
  onChange: (v: string) => void,
  id: string, // Add id parameter here
): React.ReactElement {
  switch (field.type as DolibarrFieldType) {
    case 'textarea':
      return (
        <textarea
          id={id} // Usar el id pasado como prop
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className={INPUT_CLS}
        />
      )
    case 'select': {
      const opts: DolibarrFieldOption[] = field.options ?? []
      return (
        <select id={field.key} value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS}>
          {!field.required && <option value="">— Sin valor —</option>}
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )
    }
    case 'boolean':
      return (
        <select id={field.key} value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS}>
          <option value="0">No</option>
          <option value="1">Sí</option>
        </select>
      )
    case 'number':
      return (
        <input
          type="number"
          id={field.key}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLS}
          step="any"
        />
      )
    case 'date':
      return (
        <input
          type="date"
          id={field.key}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLS}
        />
      )
    default:
      return (
        <input
          type="text"
          id={field.key}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLS}
        />
      )
  }
}

/** Coerce form string values to appropriate types for the API payload. */
function buildPayload(
  values: Record<string, string>,
  fields: DolibarrFieldSchema[],
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  const arrayOptions: Record<string, unknown> = {}

  for (const field of fields) {
    const raw = values[field.key]
    if (raw === undefined || raw === null || raw === '') continue

    let coerced: unknown = raw
    if (field.type === 'number') {
      const n = parseFloat(raw)
      if (isNaN(n)) continue
      coerced = n
    } else if ((field.type === 'select' || field.type === 'boolean') && !field.is_extra) {
      // Dolibarr expects integer values for standard select fields (type, status, weight_units…)
      if (/^-?\d+$/.test(raw)) coerced = parseInt(raw, 10)
    }

    if (field.is_extra) {
      arrayOptions[field.key] = coerced
    } else {
      payload[field.key] = coerced
    }
  }

  if (Object.keys(arrayOptions).length > 0) {
    payload.array_options = arrayOptions
  }

  return payload
}

/** Build initial form values from an existing product + field schema. */
function initFromProduct(
  product: DolibarrProduct,
  fields: DolibarrFieldSchema[],
): Record<string, string> {
  const productAny = product as unknown as Record<string, unknown>
  const values: Record<string, string> = {}

  for (const field of fields) {
    if (field.is_extra) {
      const extraVal = product.array_options?.[field.key]
      values[field.key] = extraVal != null ? String(extraVal) : ''
    } else {
      const val = productAny[field.key]
      values[field.key] = val != null ? String(val) : ''
    }
  }

  return values
}

/** Build empty initial form values with sensible defaults. */
function initEmpty(fields: DolibarrFieldSchema[]): Record<string, string> {
  const defaults: Record<string, string> = {
    status: '1',
    type: '0',
    weight_units: '0',
    length_units: '0',
    surface_units: '0',
    volume_units: '0',
  }
  const values: Record<string, string> = {}

  for (const field of fields) {
    if (defaults[field.key] !== undefined) {
      values[field.key] = defaults[field.key]
    } else if (
      field.type === 'select' &&
      field.options &&
      field.options.length > 0 &&
      !field.is_extra
    ) {
      values[field.key] = field.options[0].value
    } else {
      values[field.key] = ''
    }
  }

  return values
}

// ── Dynamic form component ───────────────────────────────────────────────

interface DynamicProductFormProps {
  fields: DolibarrFieldSchema[]
  values: Record<string, string>
  onChange: (key: string, value: string) => void
}

function DynamicProductForm({ fields, values, onChange }: DynamicProductFormProps): React.ReactElement {
  const sections = useMemo(() => {
    const map = new Map<string, DolibarrFieldSchema[]>()
    for (const f of fields) {
      const existing = map.get(f.section) ?? []
      map.set(f.section, [...existing, f])
    }
    return map
  }, [fields])

  return (
    <div className="space-y-4">
      {Array.from(sections.entries()).map(([section, sectionFields]) => (
        <div key={section} className={SECTION_CLS}>
          <p className={SECTION_TITLE_CLS}>
            {section}
            {section === 'Campos personalizados' && (
              <span className="ml-2 normal-case text-purple-500 font-normal">
                (extra fields de esta instancia)
              </span>
            )}
          </p>
          <div className="grid grid-cols-2 gap-3">
            {sectionFields.map((field) => (
              <div
                key={field.key}
                className={field.type === 'textarea' ? 'col-span-2' : ''}
              >
                <label className={LABEL_CLS}>
                  {field.label}
                  {field.required && <span className="text-red-500 ml-1">*</span>}
                </label>
                {renderFieldInput(
                  field,
                  values[field.key] ?? '',
                  (v) => onChange(field.key, v),
                  `form-field-${field.key}`, // Pass the id here
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Create modal ─────────────────────────────────────────────────────────

interface CreateProductModalProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateProductModal({ onClose, onSuccess }: CreateProductModalProps): React.ReactElement {
  const [fields, setFields] = useState<DolibarrFieldSchema[]>([])
  const [fieldsLoading, setFieldsLoading] = useState(true)
  const [values, setValues] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [categories, setCategories] = useState<DolibarrCategory[]>([])
  const [brands, setBrands] = useState<DolibarrCategory[]>([])
  const [selectedCategory, setSelectedCategory] = useState('')
  const [selectedSubcategory, setSelectedSubcategory] = useState('')
  const [selectedBrand, setSelectedBrand] = useState('')

  useEffect(() => {
    Promise.all([
      getDolibarrProductFields(),
      listDolibarrCategories('product', 200, 0).catch(() => ({ items: [] as DolibarrCategory[], total: 0, limit: 200, offset: 0, has_more: false })),
      listDolibarrBrands(200, 0).catch(() => ({ items: [] as DolibarrCategory[], total: 0, limit: 200, offset: 0, has_more: false })),
    ])
      .then(([f, cats, brnds]) => {
        setFields(f)
        setValues(initEmpty(f))
        setCategories(cats.items)
        setBrands(brnds.items)
      })
      .catch((err) => setError((err as Error).message ?? 'Error cargando campos'))
      .finally(() => setFieldsLoading(false))
  }, [])

  const selectedCatObj = categories.find((c) => c.label === selectedCategory)
  const subcategoriesCreate = selectedCatObj
    ? categories.filter((c) => {
        try { return parseInt(String(c.fk_parent)) === parseInt(String(selectedCatObj.id)) }
        catch { return false }
      })
    : []

  const handleChange = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    if (!values.ref || !values.label) {
      setError('Referencia y nombre son obligatorios')
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      const payload = buildPayload(values, fields) as Record<string, unknown>
      if (selectedBrand) {
        payload.brand_name = selectedBrand
      }
      if (selectedSubcategory) {
        payload.category_name = selectedSubcategory
      } else if (selectedCategory) {
        payload.category_name = selectedCategory
      }
      await createDolibarrProduct(payload as Partial<DolibarrProduct>)
      onSuccess()
    } catch (err) {
      setError((err as { message?: string }).message ?? 'Error creando producto')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Nuevo producto</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">
          {fieldsLoading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              Cargando campos de esta instancia Dolibarr...
            </div>
          ) : (
            <>
              <DynamicProductForm fields={fields} values={values} onChange={handleChange} />
              {brands.length > 0 && (
                <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 space-y-2">
                  <p className="text-xs font-semibold text-blue-800 uppercase tracking-wide">Marca (opcional)</p>
                  <select
                    value={selectedBrand}
                    onChange={(e) => setSelectedBrand(e.target.value)}
                    className="w-full px-3 py-2 border border-blue-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-transparent bg-white"
                  >
                    <option value="">— Sin marca —</option>
                    {brands.map((b) => (
                      <option key={b.id} value={b.label}>{b.label}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 space-y-3">
                <p className="text-xs font-semibold text-amber-800 uppercase tracking-wide">Categoría (opcional)</p>
                <p className="text-xs text-amber-700">
                  La categoría debe existir previamente en Dolibarr. Si se elige subcategoría, el producto quedará asignado a ella.
                </p>
                <select
                  value={selectedCategory}
                  onChange={(e) => { setSelectedCategory(e.target.value); setSelectedSubcategory('') }}
                  className="w-full px-3 py-2 border border-amber-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
                >
                  <option value="">— Sin categoría —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.label}>{c.label}</option>
                  ))}
                </select>
                {subcategoriesCreate.length > 0 && (
                  <select
                    value={selectedSubcategory}
                    onChange={(e) => setSelectedSubcategory(e.target.value)}
                    className="w-full px-3 py-2 border border-amber-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
                  >
                    <option value="">— Usar categoría padre —</option>
                    {subcategoriesCreate.map((c) => (
                      <option key={c.id} value={c.label}>{c.label}</option>
                    ))}
                  </select>
                )}
              </div>
            </>
          )}
        </div>
        <div className="px-6 py-4 border-t border-gray-200 space-y-3 flex-shrink-0">
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
            >
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting || fieldsLoading}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Creando...' : 'Crear producto'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Edit modal ───────────────────────────────────────────────────────────

interface EditProductModalProps {
  product: DolibarrProduct
  onClose: () => void
  onSuccess: () => void
}

function EditProductModal({ product, onClose, onSuccess }: EditProductModalProps): React.ReactElement {
  const [fields, setFields] = useState<DolibarrFieldSchema[]>([])
  const [fieldsLoading, setFieldsLoading] = useState(true)
  const [values, setValues] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wpSync, setWpSync] = useState<{ synced: boolean; reason?: string; wc_id?: number } | null>(null)
  const [categories, setCategories] = useState<DolibarrCategory[]>([])
  const [brands, setBrands] = useState<DolibarrCategory[]>([])
  const [selectedCategory, setSelectedCategory] = useState('')
  const [selectedSubcategory, setSelectedSubcategory] = useState('')
  const [selectedBrand, setSelectedBrand] = useState('')

  useEffect(() => {
    Promise.all([
      getDolibarrProductFields(),
      listDolibarrCategories('product', 200, 0).catch(() => ({ items: [] as DolibarrCategory[], total: 0, limit: 200, offset: 0, has_more: false })),
      listDolibarrBrands(200, 0).catch(() => ({ items: [] as DolibarrCategory[], total: 0, limit: 200, offset: 0, has_more: false })),
    ])
      .then(([f, cats, brnds]) => {
        setFields(f)
        setValues(initFromProduct(product, f))
        setCategories(cats.items)
        setBrands(brnds.items)
      })
      .catch((err) => setError((err as Error).message ?? 'Error cargando campos'))
      .finally(() => setFieldsLoading(false))
  }, [product])

  const selectedCatObjEdit = categories.find((c) => c.label === selectedCategory)
  const subcategoriesEdit = selectedCatObjEdit
    ? categories.filter((c) => {
        try { return parseInt(String(c.fk_parent)) === parseInt(String(selectedCatObjEdit.id)) }
        catch { return false }
      })
    : []

  const handleChange = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    if (!values.ref || !values.label) {
      setError('Referencia y nombre son obligatorios')
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      setWpSync(null)
      const payload = buildPayload(values, fields) as Record<string, unknown>
      if (selectedBrand) {
        payload.brand_name = selectedBrand
      }
      if (selectedSubcategory) {
        payload.category_name = selectedSubcategory
      } else if (selectedCategory) {
        payload.category_name = selectedCategory
      }
      const result = await updateDolibarrProduct(product.id, payload as Partial<DolibarrProduct>)
      if (result.wordpress_sync) setWpSync(result.wordpress_sync)
      onSuccess()
    } catch (err) {
      setError((err as { message?: string }).message ?? 'Error actualizando producto')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">
            Editar producto — {product.ref}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">
          {fieldsLoading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              Cargando campos de esta instancia Dolibarr...
            </div>
          ) : (
            <>
              <DynamicProductForm fields={fields} values={values} onChange={handleChange} />
              {brands.length > 0 && (
                <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 space-y-2">
                  <p className="text-xs font-semibold text-blue-800 uppercase tracking-wide">Marca (opcional)</p>
                  <select
                    value={selectedBrand}
                    onChange={(e) => setSelectedBrand(e.target.value)}
                    className="w-full px-3 py-2 border border-blue-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-transparent bg-white"
                  >
                    <option value="">— Sin cambiar —</option>
                    {brands.map((b) => (
                      <option key={b.id} value={b.label}>{b.label}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 space-y-3">
                <p className="text-xs font-semibold text-amber-800 uppercase tracking-wide">Asignar a categoría (opcional)</p>
                <p className="text-xs text-amber-700">
                  La categoría debe existir en Dolibarr. Si se elige subcategoría, el producto quedará asignado a ella. Si ya pertenece a una categoría, se añadirá además.
                </p>
                <select
                  value={selectedCategory}
                  onChange={(e) => { setSelectedCategory(e.target.value); setSelectedSubcategory('') }}
                  className="w-full px-3 py-2 border border-amber-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
                >
                  <option value="">— Sin cambiar —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.label}>{c.label}</option>
                  ))}
                </select>
                {subcategoriesEdit.length > 0 && (
                  <select
                    value={selectedSubcategory}
                    onChange={(e) => setSelectedSubcategory(e.target.value)}
                    className="w-full px-3 py-2 border border-amber-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
                  >
                    <option value="">— Usar categoría padre —</option>
                    {subcategoriesEdit.map((c) => (
                      <option key={c.id} value={c.label}>{c.label}</option>
                    ))}
                  </select>
                )}
              </div>
            </>
          )}
        </div>
        <div className="px-6 py-4 border-t border-gray-200 space-y-3 flex-shrink-0">
          {wpSync && (
            <p className={`text-xs px-3 py-2 rounded ${wpSync.synced ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
              WooCommerce: {wpSync.synced ? `sincronizado (ID ${wpSync.wc_id})` : wpSync.reason}
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
            >
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting || fieldsLoading}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Guardando...' : 'Guardar cambios'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── CSV Import modal ─────────────────────────────────────────────────────

type CsvImportStep = 'upload' | 'mapping' | 'importing' | 'results'

interface CsvImportModalProps {
  onClose: () => void
  onSuccess: () => void
}

/**
 * Modal multi-paso para importación masiva de productos desde CSV a Dolibarr.
 *
 * Paso 1 — Upload: usuario selecciona el CSV.
 * Paso 2 — Mapping: mapea cada columna CSV a un campo Dolibarr.
 * Paso 3 — Importing: progreso en curso.
 * Paso 4 — Results: resumen de creados/actualizados/omitidos/errores.
 *
 * @author BenjaminDTS | Carlos Vico
 */
function CsvImportModal({ onClose, onSuccess }: CsvImportModalProps): React.ReactElement {
  const [step, setStep] = useState<CsvImportStep>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<CsvImportPreview | null>(null)
  const [fields, setFields] = useState<DolibarrFieldSchema[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [overwrite, setOverwrite] = useState(false)
  const [categoryColumn, setCategoryColumn] = useState('')
  const [subcategoryColumn, setSubcategoryColumn] = useState('')
  const [brandColumn, setBrandColumn] = useState('')
  const [result, setResult] = useState<DolibarrImportTask['results'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [importProgress, setImportProgress] = useState<{ processed: number; total: number }>({ processed: 0, total: 0 })
  const [importMessage, setImportMessage] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  useEffect(() => {
    getDolibarrProductFields()
      .then(setFields)
      .catch(() => {})
  }, [])

  const processFile = async (f: File) => {
    setFile(f)
    setError(null)
    setLoading(true)
    try {
      const data = await previewDolibarrCsv(f)
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    processFile(f)
  }

  const handleImport = async () => {
    const activeMapping = Object.fromEntries(
      Object.entries(mapping).filter(([, v]) => v !== '')
    )
    if (!Object.values(activeMapping).includes('ref')) {
      setError("Debes asignar al menos una columna al campo 'ref' (Referencia).")
      return
    }
    if (!file) return
    setError(null)
    setImportProgress({ processed: 0, total: 0 })
    setImportMessage('')
    setStep('importing')

    try {
      const task = await importDolibarrCsv(file, activeMapping, overwrite, categoryColumn || undefined, subcategoryColumn || undefined, brandColumn || undefined)

      pollRef.current = setInterval(async () => {
        try {
          const status = await getDolibarrImportStatus(task.task_id)
          setImportProgress(status.progress)
          setImportMessage(status.message)

          if (status.status === 'completed' && status.results) {
            clearInterval(pollRef.current!)
            pollRef.current = null
            setResult(status.results)
            setStep('results')
            if (status.results.created > 0 || status.results.updated > 0) onSuccess()
          } else if (status.status === 'failed') {
            clearInterval(pollRef.current!)
            pollRef.current = null
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

  const allFieldOptions = useMemo(() => {
    const opts: { value: string; label: string }[] = [{ value: '', label: '— Ignorar columna —' }]
    for (const f of fields) {
      opts.push({ value: f.key, label: `${f.label}${f.required ? ' *' : ''} (${f.section})` })
    }
    return opts
  }, [fields])

  const refMapped = Object.values(mapping).includes('ref')

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

          {/* ── Step 1: Upload ── */}
          {step === 'upload' && (
            <div className="space-y-4">
              <div
                onClick={() => fileInputRef.current?.click()}
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) processFile(f) }}
                onDragOver={(e) => e.preventDefault()}
                className="border-2 border-dashed border-gray-300 rounded-lg p-10 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.tsv,.txt"
                  className="hidden"
                  onChange={handleFileChange}
                />
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

              {file && (
                <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
                  <span className="font-medium">{file.name}</span>
                  {' · '}
                  {(file.size / 1024).toFixed(1)} KB
                </div>
              )}

              {loading && (
                <p className="text-sm text-gray-500 text-center">Analizando CSV...</p>
              )}
              {error && (
                <div className="bg-red-50 border-l-4 border-red-400 p-3 rounded text-sm text-red-700">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Mapping ── */}
          {step === 'mapping' && preview && (
            <div className="space-y-5">
              {/* Overwrite toggle */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(e) => setOverwrite(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-blue-900">Actualizar productos existentes</p>
                    <p className="text-xs text-blue-700 mt-0.5">
                      Si está activo, los productos con la misma <strong>Referencia</strong> se actualizarán con los datos del CSV.
                      Si está inactivo, se omiten y solo se crean los nuevos.
                    </p>
                  </div>
                </label>
              </div>

              {/* Preview table */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Previsualización — primeras {preview.preview.length} filas
                </p>
                <div className="overflow-x-auto rounded border border-gray-200 text-xs">
                  <table className="min-w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        {preview.headers.map((h) => (
                          <th key={h} className="px-3 py-2 text-left font-medium text-gray-700 whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {preview.preview.map((row, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          {preview.headers.map((h) => (
                            <td key={h} className="px-3 py-2 text-gray-600 max-w-[160px] truncate">{row[h]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Mapping */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Mapeo de columnas — {Object.values(mapping).filter(Boolean).length} mapeadas de {preview.headers.length}
                </p>
                <div className="space-y-2">
                  {preview.headers.map((header) => (
                    <div key={header} className="flex items-center gap-3">
                      <span className="w-40 text-sm font-medium text-gray-700 truncate shrink-0" title={header}>
                        {header}
                      </span>
                      <span className="text-gray-400 shrink-0">→</span>
                      <select
                        value={mapping[header] ?? ''}
                        onChange={(e) => setMapping((prev) => ({ ...prev, [header]: e.target.value }))}
                        className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      >
                        {allFieldOptions.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>

              {/* Brand column selector */}
              <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 space-y-3">
                <p className="text-xs font-semibold text-blue-800 uppercase tracking-wide">Marca (opcional)</p>
                <p className="text-xs text-blue-700">
                  Mapea una columna del CSV a la marca del producto. Cada valor se creará automáticamente como subcategoría bajo <strong>"Marcas"</strong> si no existe.
                  La categoría padre <strong>"Marcas"</strong> debe existir previamente en Dolibarr.
                </p>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-blue-800 shrink-0 w-36">Columna marca:</span>
                  <select
                    value={brandColumn}
                    onChange={(e) => setBrandColumn(e.target.value)}
                    className="flex-1 px-2 py-1.5 border border-blue-300 rounded text-sm focus:ring-2 focus:ring-blue-400 focus:border-transparent bg-white"
                  >
                    <option value="">— No asignar marca —</option>
                    {preview?.headers.map((h) => (
                      <option key={h} value={h}>{h}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Category + Subcategory column selectors */}
              <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 space-y-3">
                <p className="text-xs font-semibold text-amber-800 uppercase tracking-wide">Categorías (opcional)</p>
                <p className="text-xs text-amber-700">
                  ⚠ La categoría debe existir previamente en Dolibarr. Si se indica subcategoría, se creará automáticamente bajo la categoría padre si no existe. El producto quedará asignado a la subcategoría.
                </p>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-amber-800 shrink-0 w-36">Columna categoría:</span>
                  <select
                    value={categoryColumn}
                    onChange={(e) => { setCategoryColumn(e.target.value); if (!e.target.value) setSubcategoryColumn('') }}
                    className="flex-1 px-2 py-1.5 border border-amber-300 rounded text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
                  >
                    <option value="">— No asignar categoría —</option>
                    {preview?.headers.map((h) => (
                      <option key={h} value={h}>{h}</option>
                    ))}
                  </select>
                </div>
                {categoryColumn && (
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-amber-800 shrink-0 w-36">Columna subcategoría:</span>
                    <select
                      value={subcategoryColumn}
                      onChange={(e) => setSubcategoryColumn(e.target.value)}
                      className="flex-1 px-2 py-1.5 border border-amber-300 rounded text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
                    >
                      <option value="">— Sin subcategoría —</option>
                      {preview?.headers.map((h) => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {!refMapped && (
                <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                  Asigna al menos una columna al campo <strong>Referencia (ref)</strong> para poder importar.
                </p>
              )}

              {error && (
                <div className="bg-red-50 border-l-4 border-red-400 p-3 rounded text-sm text-red-700">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* ── Step 3: Importing ── */}
          {step === 'importing' && (
            <div className="flex flex-col items-center justify-center py-16 space-y-5">
              <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
              {importProgress.total > 0 ? (
                <>
                  <p className="text-gray-700 text-sm font-medium">
                    {importProgress.processed} / {importProgress.total} productos
                  </p>
                  <div className="w-full max-w-xs bg-gray-200 rounded-full h-2.5">
                    <div
                      className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
                      style={{ width: `${Math.round((importProgress.processed / importProgress.total) * 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500">
                    {Math.round((importProgress.processed / importProgress.total) * 100)}% completado
                  </p>
                  {importMessage && (
                    <p className="text-xs text-gray-400 max-w-xs text-center">{importMessage}</p>
                  )}
                </>
              ) : (
                <>
                  <p className="text-gray-600 text-sm">Iniciando importación en segundo plano...</p>
                  <p className="text-gray-400 text-xs">Las importaciones grandes pueden tardar más de una hora.</p>
                </>
              )}
            </div>
          )}

          {/* ── Step 4: Results ── */}
          {step === 'results' && result && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
                  <p className="text-3xl font-bold text-green-700">{result.created}</p>
                  <p className="text-xs text-green-600 mt-1">Creados</p>
                </div>
                <div className={`border rounded-lg p-4 text-center ${result.updated > 0 ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'}`}>
                  <p className={`text-3xl font-bold ${result.updated > 0 ? 'text-blue-700' : 'text-gray-400'}`}>{result.updated}</p>
                  <p className={`text-xs mt-1 ${result.updated > 0 ? 'text-blue-600' : 'text-gray-400'}`}>Actualizados</p>
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
                  <p className="text-3xl font-bold text-gray-400">{result.skipped}</p>
                  <p className="text-xs text-gray-400 mt-1">Omitidos</p>
                </div>
                <div className={`border rounded-lg p-4 text-center ${result.errors > 0 ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'}`}>
                  <p className={`text-3xl font-bold ${result.errors > 0 ? 'text-red-700' : 'text-gray-400'}`}>{result.errors}</p>
                  <p className={`text-xs mt-1 ${result.errors > 0 ? 'text-red-600' : 'text-gray-400'}`}>Errores</p>
                </div>
              </div>

              {result.errors > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Filas con error</p>
                  <div className="max-h-40 overflow-y-auto space-y-1">
                    {result.results
                      .filter((r) => r.action === 'error')
                      .map((r) => (
                        <div key={r.row} className="text-xs bg-red-50 border border-red-100 rounded px-3 py-2 text-red-700">
                          <span className="font-medium">Fila {r.row}</span>
                          {r.ref && <span className="text-gray-500 ml-1">({r.ref})</span>}
                          {' — '}{r.error}
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {categoryColumn && result.results.some((r) => r.category_assigned) && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Categorías asignadas</p>
                  <p className="text-xs text-gray-600">
                    {result.results.filter((r) => r.category_assigned).length} productos asignados a categoría correctamente.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex gap-3 flex-shrink-0">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
          >
            {step === 'results' ? 'Cerrar' : 'Cancelar'}
          </button>

          {step === 'mapping' && (
            <>
              <button
                onClick={() => { setStep('upload'); setPreview(null); setFile(null) }}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
              >
                ← Volver
              </button>
              <button
                onClick={handleImport}
                disabled={!refMapped}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
              >
                Importar {preview?.total_rows ?? ''} productos →
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sync modal (unchanged) ───────────────────────────────────────────────

interface SyncModalProps {
  onClose: () => void
  onSuccess: () => void
}

function SyncFromJobModal({ onClose, onSuccess }: SyncModalProps): React.ReactElement {
  const [jobId, setJobId] = useState('')
  const [overwrite, setOverwrite] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{
    created: number
    updated: number
    omitted: number
  } | null>(null)

  const handleSync = async (): Promise<void> => {
    if (!jobId) {
      alert('Selecciona un job')
      return
    }
    try {
      setLoading(true)
      const results = await syncDolibarrFromJob({
        job_id: jobId,
        product_codes: [],
        overwrite,
      })
      setResult({
        created: results.filter((r) => r.action === 'created').length,
        updated: results.filter((r) => r.action === 'updated').length,
        omitted: results.filter((r) => r.error !== null).length,
      })
    } catch (err) {
      alert(`Error: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Sincronizar desde job</h3>

        {!result ? (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ID del job</label>
              <input
                type="text"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                placeholder="Ej: abc123..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
              />
              <span className="text-sm text-gray-700">Sobreescribir productos existentes</span>
            </label>
            <div className="flex gap-3 pt-4">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleSync}
                disabled={loading || !jobId}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Sincronizando...' : 'Sincronizar'}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded p-4">
              <p className="text-sm text-green-800">
                <strong>{result.created}</strong> creados ·{' '}
                <strong>{result.updated}</strong> actualizados ·{' '}
                <strong>{result.omitted}</strong> omitidos
              </p>
            </div>
            <button
              onClick={onSuccess}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Cerrar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
