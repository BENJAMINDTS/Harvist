/**
 * Módulo de gestión de productos de Dolibarr.
 * El formulario de creación/edición es completamente dinámico:
 * obtiene el schema de campos desde el endpoint /products/fields,
 * que combina campos estándar con los extra fields configurados en esa instancia.
 *
 * @author BenjaminDTS
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  listDolibarrProducts,
  deleteDolibarrProduct,
  syncDolibarrFromJob,
  createDolibarrProduct,
  updateDolibarrProduct,
  getDolibarrProductFields,
  previewDolibarrCsv,
  importDolibarrCsv,
} from '@/api/client'
import {
  type DolibarrProduct,
  type DolibarrFieldSchema,
  type DolibarrFieldType,
  type DolibarrFieldOption,
  type CsvImportPreview,
  type CsvImportResponse,
} from '@/types/dolibarr'

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

  const loadProducts = async (limit = 10, offset = 0) => {
    try {
      setLoading(true)
      const data = await listDolibarrProducts(limit, offset)
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
  }

  useEffect(() => {
    loadProducts()
  }, [])

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este producto?')) return
    try {
      await deleteDolibarrProduct(id)
      loadProducts(pagination.limit, pagination.offset)
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando producto')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex gap-4">
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          + Nuevo producto
        </button>
        <button
          onClick={() => setShowSyncModal(true)}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
        >
          ↓ Sincronizar desde job
        </button>
        <button
          onClick={() => setShowCsvImportModal(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
        >
          ↑ Importar CSV
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
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  Cargando productos...
                </td>
              </tr>
            ) : products.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                  Sin productos
                </td>
              </tr>
            ) : (
              products.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
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
                        onClick={() => handleDelete(p.id)}
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

      {pagination.total > 0 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>
            {pagination.offset + 1} -{' '}
            {Math.min(pagination.offset + pagination.limit, pagination.total)} de{' '}
            {pagination.total}
          </div>
          <div className="flex gap-2">
            <button
              disabled={pagination.offset === 0}
              onClick={() =>
                loadProducts(pagination.limit, Math.max(0, pagination.offset - pagination.limit))
              }
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              disabled={!pagination.has_more}
              onClick={() =>
                loadProducts(pagination.limit, pagination.offset + pagination.limit)
              }
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}

      {showCreateModal && (
        <CreateProductModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false)
            loadProducts(pagination.limit, pagination.offset)
          }}
        />
      )}

      {editingProduct && (
        <EditProductModal
          product={editingProduct}
          onClose={() => setEditingProduct(null)}
          onSuccess={() => {
            setEditingProduct(null)
            loadProducts(pagination.limit, pagination.offset)
          }}
        />
      )}

      {showSyncModal && (
        <SyncFromJobModal
          onClose={() => setShowSyncModal(false)}
          onSuccess={() => {
            setShowSyncModal(false)
            loadProducts()
          }}
        />
      )}

      {showCsvImportModal && (
        <CsvImportModal
          onClose={() => setShowCsvImportModal(false)}
          onSuccess={() => {
            setShowCsvImportModal(false)
            loadProducts()
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
): React.ReactElement {
  switch (field.type as DolibarrFieldType) {
    case 'textarea':
      return (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className={INPUT_CLS}
        />
      )
    case 'select': {
      const opts: DolibarrFieldOption[] = field.options ?? []
      return (
        <select value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS}>
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
        <select value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS}>
          <option value="0">No</option>
          <option value="1">Sí</option>
        </select>
      )
    case 'number':
      return (
        <input
          type="number"
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
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLS}
        />
      )
    default:
      return (
        <input
          type="text"
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

function DynamicProductForm({ fields, values, onChange }: DynamicProductFormProps) {
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
                {renderFieldInput(field, values[field.key] ?? '', (v) =>
                  onChange(field.key, v),
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

function CreateProductModal({ onClose, onSuccess }: CreateProductModalProps) {
  const [fields, setFields] = useState<DolibarrFieldSchema[]>([])
  const [fieldsLoading, setFieldsLoading] = useState(true)
  const [values, setValues] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getDolibarrProductFields()
      .then((f) => {
        setFields(f)
        setValues(initEmpty(f))
      })
      .catch((err) => setError((err as Error).message ?? 'Error cargando campos'))
      .finally(() => setFieldsLoading(false))
  }, [])

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
      await createDolibarrProduct(buildPayload(values, fields) as Partial<DolibarrProduct>)
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error creando producto')
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
        <div className="overflow-y-auto flex-1 px-6 py-4">
          {fieldsLoading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              Cargando campos de esta instancia Dolibarr...
            </div>
          ) : (
            <DynamicProductForm fields={fields} values={values} onChange={handleChange} />
          )}
        </div>
        <div className="px-6 py-4 border-t border-gray-200 space-y-3">
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

function EditProductModal({ product, onClose, onSuccess }: EditProductModalProps) {
  const [fields, setFields] = useState<DolibarrFieldSchema[]>([])
  const [fieldsLoading, setFieldsLoading] = useState(true)
  const [values, setValues] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getDolibarrProductFields()
      .then((f) => {
        setFields(f)
        setValues(initFromProduct(product, f))
      })
      .catch((err) => setError((err as Error).message ?? 'Error cargando campos'))
      .finally(() => setFieldsLoading(false))
  }, [product])

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
      await updateDolibarrProduct(
        product.id,
        buildPayload(values, fields) as Partial<DolibarrProduct>,
      )
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error actualizando producto')
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
        <div className="overflow-y-auto flex-1 px-6 py-4">
          {fieldsLoading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              Cargando campos de esta instancia Dolibarr...
            </div>
          ) : (
            <DynamicProductForm fields={fields} values={values} onChange={handleChange} />
          )}
        </div>
        <div className="px-6 py-4 border-t border-gray-200 space-y-3">
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
function CsvImportModal({ onClose, onSuccess }: CsvImportModalProps) {
  const [step, setStep] = useState<CsvImportStep>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<CsvImportPreview | null>(null)
  const [fields, setFields] = useState<DolibarrFieldSchema[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [overwrite, setOverwrite] = useState(false)
  const [result, setResult] = useState<CsvImportResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getDolibarrProductFields()
      .then(setFields)
      .catch(() => {})
  }, [])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
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
    setStep('importing')
    try {
      const res = await importDolibarrCsv(file, activeMapping, overwrite)
      setResult(res)
      setStep('results')
    } catch (err) {
      setError((err as { message?: string }).message ?? 'Error durante la importación')
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
      <div className="bg-white rounded-lg shadow-lg w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Importar productos desde CSV</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {step === 'upload' && 'Selecciona el archivo CSV'}
              {step === 'mapping' && `${preview?.total_rows ?? 0} filas detectadas — asigna las columnas`}
              {step === 'importing' && 'Importando productos a Dolibarr...'}
              {step === 'results' && 'Importación completada'}
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
                className="border-2 border-dashed border-gray-300 rounded-lg p-10 text-center cursor-pointer hover:border-purple-400 hover:bg-purple-50 transition-colors"
              >
                <p className="text-gray-500 text-sm">Haz clic para seleccionar un archivo CSV</p>
                <p className="text-gray-400 text-xs mt-1">UTF-8 o Latin-1 · Máximo 10 MB</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={handleFileChange}
              />
              {loading && (
                <p className="text-sm text-gray-500 text-center">Analizando CSV...</p>
              )}
              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>
          )}

          {/* ── Step 2: Mapping ── */}
          {step === 'mapping' && preview && (
            <div className="space-y-5">
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
                  Mapeo de columnas
                </p>
                <div className="space-y-2">
                  {preview.headers.map((header) => (
                    <div key={header} className="flex items-center gap-3">
                      <span className="w-40 text-xs font-mono bg-gray-100 px-2 py-1 rounded truncate flex-shrink-0 text-gray-700">
                        {header}
                      </span>
                      <span className="text-gray-400 text-xs">→</span>
                      <select
                        value={mapping[header] ?? ''}
                        onChange={(e) => setMapping((prev) => ({ ...prev, [header]: e.target.value }))}
                        className="flex-1 text-xs px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      >
                        {allFieldOptions.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>

              {/* Overwrite toggle */}
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={overwrite}
                  onChange={(e) => setOverwrite(e.target.checked)}
                  className="rounded"
                />
                Sobreescribir productos existentes (busca por referencia)
              </label>

              {!refMapped && (
                <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                  Asigna al menos una columna al campo <strong>Referencia (ref)</strong> para poder importar.
                </p>
              )}

              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>
          )}

          {/* ── Step 3: Importing ── */}
          {step === 'importing' && (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <div className="w-10 h-10 border-4 border-purple-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-gray-600 text-sm">Importando {preview?.total_rows ?? '...'} productos a Dolibarr...</p>
              <p className="text-gray-400 text-xs">Esto puede tardar varios minutos para catálogos grandes.</p>
            </div>
          )}

          {/* ── Step 4: Results ── */}
          {step === 'results' && result && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Creados', value: result.created, color: 'bg-green-100 text-green-800' },
                  { label: 'Actualizados', value: result.updated, color: 'bg-blue-100 text-blue-800' },
                  { label: 'Omitidos', value: result.skipped, color: 'bg-gray-100 text-gray-700' },
                  { label: 'Errores', value: result.errors, color: 'bg-red-100 text-red-800' },
                ].map(({ label, value, color }) => (
                  <div key={label} className={`rounded-lg p-3 text-center ${color}`}>
                    <p className="text-2xl font-bold">{value}</p>
                    <p className="text-xs font-medium mt-0.5">{label}</p>
                  </div>
                ))}
              </div>

              {result.errors > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Filas con error</p>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {result.results
                      .filter((r) => r.action === 'error')
                      .map((r) => (
                        <div key={r.row} className="text-xs bg-red-50 border border-red-200 rounded px-3 py-2">
                          <span className="font-medium">Fila {r.row}</span>
                          {r.ref && <span className="text-gray-500 ml-1">({r.ref})</span>}
                          {' — '}{r.error}
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex gap-3">
          {step === 'upload' && (
            <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">
              Cancelar
            </button>
          )}

          {step === 'mapping' && (
            <>
              <button
                onClick={() => { setStep('upload'); setPreview(null); setFile(null) }}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
              >
                ← Cambiar archivo
              </button>
              <button
                onClick={handleImport}
                disabled={!refMapped}
                className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium"
              >
                Importar {preview?.total_rows ?? ''} productos →
              </button>
            </>
          )}

          {step === 'results' && (
            <button
              onClick={onSuccess}
              className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium"
            >
              Cerrar y actualizar lista
            </button>
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

function SyncFromJobModal({ onClose, onSuccess }: SyncModalProps) {
  const [jobId, setJobId] = useState('')
  const [overwrite, setOverwrite] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{
    created: number
    updated: number
    omitted: number
  } | null>(null)

  const handleSync = async () => {
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
