/**
 * Módulo de gestión de campos extra (extrafields) de Dolibarr.
 *
 * Permite crear, visualizar y eliminar atributos personalizados
 * para productos. Los cambios se reflejan de inmediato tanto en
 * Harvist como en la interfaz de Dolibarr.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import {
  listDolibarrExtraFields,
  createDolibarrExtraField,
  deleteDolibarrExtraField,
} from '@/api/client'
import { type DolibarrExtraField, type DolibarrExtraFieldCreate } from '@/types/dolibarr'

const SUPPORTED_TYPES: Array<{ value: string; label: string }> = [
  { value: 'varchar', label: 'Texto corto (varchar)' },
  { value: 'text', label: 'Texto largo' },
  { value: 'int', label: 'Número entero (int)' },
  { value: 'double', label: 'Número decimal (double)' },
  { value: 'price', label: 'Precio' },
  { value: 'date', label: 'Fecha' },
  { value: 'datetime', label: 'Fecha y hora' },
  { value: 'boolean', label: 'Sí / No (boolean)' },
  { value: 'select', label: 'Lista desplegable (select)' },
  { value: 'html', label: 'HTML / Editor rico' },
  { value: 'phone', label: 'Teléfono' },
  { value: 'mail', label: 'Email' },
  { value: 'url', label: 'URL' },
]

const ELEMENTTYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'product', label: 'Productos' },
  { value: 'societe', label: 'Terceros' },
  { value: 'facture', label: 'Facturas cliente' },
  { value: 'facture_fourn', label: 'Facturas proveedor' },
  { value: 'commande', label: 'Pedidos cliente' },
  { value: 'commande_fournisseur', label: 'Pedidos proveedor' },
]

const TYPE_BADGE: Record<string, string> = {
  varchar: 'bg-blue-100 text-blue-800',
  text: 'bg-blue-100 text-blue-800',
  html: 'bg-purple-100 text-purple-800',
  int: 'bg-green-100 text-green-800',
  double: 'bg-green-100 text-green-800',
  price: 'bg-green-100 text-green-800',
  date: 'bg-yellow-100 text-yellow-800',
  datetime: 'bg-yellow-100 text-yellow-800',
  boolean: 'bg-gray-100 text-gray-800',
  select: 'bg-orange-100 text-orange-800',
  phone: 'bg-blue-100 text-blue-800',
  mail: 'bg-blue-100 text-blue-800',
  url: 'bg-blue-100 text-blue-800',
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'

export default function DolibarrExtraFields() {
  const [fields, setFields] = useState<DolibarrExtraField[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dbNotConfigured, setDbNotConfigured] = useState(false)
  const [elementtype, setElementtype] = useState('product')
  const [showCreateModal, setShowCreateModal] = useState(false)

  const loadFields = async (et = elementtype) => {
    try {
      setLoading(true)
      setError(null)
      const data = await listDolibarrExtraFields(et)
      setFields(data)
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando campos extra')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFields(elementtype)
  }, [elementtype])

  const handleDelete = async (attrname: string) => {
    if (!confirm(`¿Eliminar el campo extra "${attrname}"? Esta acción no se puede deshacer.`))
      return
    try {
      await deleteDolibarrExtraField(attrname, elementtype)
      loadFields(elementtype)
    } catch (err) {
      const msg = (err as Error).message ?? 'Error eliminando campo extra'
      if (msg.includes('BD_NO_CONFIGURADA')) setDbNotConfigured(true)
      else setError(msg)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-gray-700">Elemento:</label>
          <select
            value={elementtype}
            onChange={(e) => setElementtype(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
          >
            {ELEMENTTYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
        >
          + Nuevo campo extra
        </button>
      </div>

      {dbNotConfigured && (
        <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded text-sm text-amber-900 space-y-2">
          <p className="font-semibold">Acceso a BD no configurado</p>
          <p>
            La creación de campos extra usa acceso directo a MySQL (mismo método que los scripts Python).
            Configura las credenciales en la pestaña{' '}
            <strong>Configuración → BD Dolibarr</strong>:
          </p>
          <ul className="list-disc list-inside text-xs space-y-1 text-amber-800">
            <li>Host MySQL (ej: <code>localhost</code>)</li>
            <li>Puerto (por defecto <code>3306</code>)</li>
            <li>Nombre de la BD de Dolibarr</li>
            <li>Usuario y contraseña MySQL</li>
          </ul>
          <button
            onClick={() => setDbNotConfigured(false)}
            className="text-xs text-amber-700 underline"
          >
            Cerrar aviso
          </button>
        </div>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded p-3 text-xs text-blue-700">
        <strong>Nota:</strong> Los campos se crean via acceso directo a MySQL (INSERT en{' '}
        <code>llx_extrafields</code> + ALTER TABLE). Requiere credenciales BD en{' '}
        <strong>Configuración → BD Dolibarr</strong>.
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
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Nombre interno
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Etiqueta
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Tipo</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Requerido
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Por defecto
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500 text-sm">
                  Cargando campos extra...
                </td>
              </tr>
            ) : fields.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-500 text-sm">
                  No hay campos extra configurados para este elemento.
                </td>
              </tr>
            ) : (
              fields.map((f) => (
                <tr key={f.attrname} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-mono text-gray-900">{f.attrname}</td>
                  <td className="px-6 py-4 text-sm text-gray-900">{f.label}</td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        TYPE_BADGE[f.type] ?? 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {f.type}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    {f.required ? (
                      <span className="text-green-600 font-medium">Sí</span>
                    ) : (
                      <span className="text-gray-400">No</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 font-mono">
                    {f.fielddefault || '—'}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => handleDelete(f.attrname)}
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


      {showCreateModal && (
        <CreateExtraFieldModal
          defaultElementtype={elementtype}
          onClose={() => setShowCreateModal(false)}
          onDbNotConfigured={() => {
            setShowCreateModal(false)
            setDbNotConfigured(true)
          }}
          onSuccess={() => {
            setShowCreateModal(false)
            loadFields(elementtype)
          }}
        />
      )}
    </div>
  )
}

// ── Modal de creación ──────────────────────────────────────────────────────

interface CreateExtraFieldModalProps {
  defaultElementtype: string
  onClose: () => void
  onSuccess: () => void
  onDbNotConfigured: () => void
}

const EMPTY_FORM: DolibarrExtraFieldCreate = {
  attrname: '',
  label: '',
  type: 'varchar',
  elementtype: 'product',
  size: '255',
  required: false,
  fielddefault: '',
}

function CreateExtraFieldModal({
  defaultElementtype,
  onClose,
  onSuccess,
  onDbNotConfigured,
}: CreateExtraFieldModalProps) {
  const [form, setForm] = useState<DolibarrExtraFieldCreate>({
    ...EMPTY_FORM,
    elementtype: defaultElementtype,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof DolibarrExtraFieldCreate>(
    key: K,
    value: DolibarrExtraFieldCreate[K],
  ) => setForm((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    if (!form.attrname || !form.label) {
      setError('Nombre interno y etiqueta son obligatorios.')
      return
    }
    if (!/^[a-z0-9_]+$/.test(form.attrname)) {
      setError('Nombre interno: solo minúsculas, números y guión bajo (_).')
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      await createDolibarrExtraField(form)
      onSuccess()
    } catch (err) {
      const msg = (err as Error).message ?? 'Error creando campo extra'
      if (msg.includes('BD_NO_CONFIGURADA')) {
        onDbNotConfigured()
      } else {
        setError(msg)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-lg">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Nuevo campo extra</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={LABEL_CLS}>
                Nombre interno <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={form.attrname}
                onChange={(e) => set('attrname', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                placeholder="mi_campo"
                className={INPUT_CLS}
              />
              <p className="text-xs text-gray-400 mt-1">Solo minúsculas, números y _</p>
            </div>
            <div>
              <label className={LABEL_CLS}>
                Etiqueta <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={form.label}
                onChange={(e) => set('label', e.target.value)}
                placeholder="Mi campo personalizado"
                className={INPUT_CLS}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={LABEL_CLS}>Tipo de campo</label>
              <select
                value={form.type}
                onChange={(e) => set('type', e.target.value)}
                className={INPUT_CLS}
              >
                {SUPPORTED_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLS}>Elemento Dolibarr</label>
              <select
                value={form.elementtype}
                onChange={(e) => set('elementtype', e.target.value)}
                className={INPUT_CLS}
              >
                {ELEMENTTYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {form.type === 'varchar' && (
              <div>
                <label className={LABEL_CLS}>Tamaño (caracteres)</label>
                <input
                  type="number"
                  value={form.size}
                  onChange={(e) => set('size', e.target.value)}
                  min={1}
                  max={255}
                  className={INPUT_CLS}
                />
              </div>
            )}
            <div>
              <label className={LABEL_CLS}>Valor por defecto</label>
              <input
                type="text"
                value={form.fielddefault}
                onChange={(e) => set('fielddefault', e.target.value)}
                className={INPUT_CLS}
              />
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.required}
              onChange={(e) => set('required', e.target.checked)}
              className="rounded border-gray-300 text-purple-600 focus:ring-purple-500"
            />
            <span className="text-sm text-gray-700">Campo obligatorio</span>
          </label>

          {form.type === 'select' && (
            <div className="bg-amber-50 border border-amber-200 rounded p-3">
              <p className="text-xs text-amber-800">
                Para campos de tipo <strong>select</strong>, añade las opciones desde la interfaz
                de Dolibarr tras crear el campo (Admin → Otros atributos).
              </p>
            </div>
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
              disabled={submitting}
              className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Creando...' : 'Crear campo extra'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
