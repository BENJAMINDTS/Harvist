/**
 * Panel de partners (clientes/proveedores) de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { listOdooPartners, updateOdooPartner, deleteOdooPartner } from '@/api/client'
import type { OdooPartner, PartnerMode } from '@/types/odoo'

const formatField = (v: [number, string] | false | string | undefined) => {
  if (!v) return '—'
  if (Array.isArray(v)) return v[1]
  return String(v)
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'
const SECTION_CLS = 'border border-gray-100 rounded-lg p-4 space-y-3'
const SECTION_TITLE_CLS = 'text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3'

export default function OdooPartners() {
  const [partners, setPartners] = useState<OdooPartner[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<PartnerMode>('all')
  const [search, setSearch] = useState('')
  const [editingPartner, setEditingPartner] = useState<OdooPartner | null>(null)
  const [pagination, setPagination] = useState({ limit: 10, offset: 0, total: 0, has_more: false })

  const load = async (limit = 10, offset = 0, m: PartnerMode = mode, q = search) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listOdooPartners(m, limit, offset, q)
      setPartners(data.items)
      setPagination({ limit: data.limit, offset: data.offset, total: data.total, has_more: data.has_more })
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando partners')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleMode = (m: PartnerMode) => { setMode(m); load(10, 0, m) }

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este partner de Odoo?')) return
    try {
      await deleteOdooPartner(id)
      load(pagination.limit, pagination.offset)
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando partner')
    }
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
            className={`px-4 py-2 rounded-lg font-medium transition-colors text-sm ${
              mode === m.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
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

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Nombre</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Email</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Teléfono</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Ciudad</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">NIF</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Tipo</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Cargando partners...</td></tr>
            ) : partners.length === 0 ? (
              <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-500">Sin partners</td></tr>
            ) : partners.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{p.name}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(p.email)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(p.phone)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(p.city)}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatField(p.vat)}</td>
                <td className="px-6 py-4 text-sm">
                  <div className="flex gap-1">
                    {p.customer_rank > 0 && (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">Cliente</span>
                    )}
                    {p.supplier_rank > 0 && (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">Proveedor</span>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4 text-sm">
                  <div className="flex gap-3">
                    <button
                      onClick={() => setEditingPartner(p)}
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

      {editingPartner && (
        <EditPartnerModal
          partner={editingPartner}
          onClose={() => setEditingPartner(null)}
          onSuccess={() => {
            setEditingPartner(null)
            load(pagination.limit, pagination.offset)
          }}
        />
      )}
    </div>
  )
}

// ── Edit modal ────────────────────────────────────────────────────────────

interface EditPartnerModalProps {
  partner: OdooPartner
  onClose: () => void
  onSuccess: () => void
}

function EditPartnerModal({ partner, onClose, onSuccess }: EditPartnerModalProps) {
  const str = (v: string | false | boolean | number | undefined) =>
    v == null || v === false ? '' : String(v)

  const [values, setValues] = useState({
    name: partner.name,
    email: str(partner.email),
    phone: str(partner.phone),
    mobile: str(partner.mobile),
    street: str(partner.street),
    city: str(partner.city),
    zip: str(partner.zip),
    vat: str(partner.vat),
    is_company: partner.is_company ? '1' : '0',
    active: partner.active ? '1' : '0',
    customer_rank: String(partner.customer_rank),
    supplier_rank: String(partner.supplier_rank),
    comment: str(partner.comment),
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    if (!values.name.trim()) { setError('El nombre es obligatorio.'); return }
    setError(null)
    setSubmitting(true)
    try {
      await updateOdooPartner(partner.id, {
        name: values.name.trim(),
        email: values.email.trim() || false,
        phone: values.phone.trim() || false,
        mobile: values.mobile.trim() || false,
        street: values.street.trim() || false,
        city: values.city.trim() || false,
        zip: values.zip.trim() || false,
        vat: values.vat.trim() || false,
        is_company: values.is_company === '1',
        active: values.active === '1',
        customer_rank: parseInt(values.customer_rank, 10) || 0,
        supplier_rank: parseInt(values.supplier_rank, 10) || 0,
        comment: values.comment.trim() || false,
      } as Partial<OdooPartner>)
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error actualizando partner')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <h3 className="text-lg font-semibold text-gray-900">Editar partner — {partner.name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">

          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Información general</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className={LABEL_CLS}>Nombre <span className="text-red-500">*</span></label>
                <input type="text" value={values.name} onChange={(e) => set('name', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Tipo</label>
                <select value={values.is_company} onChange={(e) => set('is_company', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Empresa</option>
                  <option value="0">Persona</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Activo</label>
                <select value={values.active} onChange={(e) => set('active', e.target.value)} className={INPUT_CLS}>
                  <option value="1">Sí</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>NIF / CIF</label>
                <input type="text" value={values.vat} onChange={(e) => set('vat', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Contacto</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Email</label>
                <input type="email" value={values.email} onChange={(e) => set('email', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Teléfono</label>
                <input type="text" value={values.phone} onChange={(e) => set('phone', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Móvil</label>
                <input type="text" value={values.mobile} onChange={(e) => set('mobile', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Dirección</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className={LABEL_CLS}>Calle</label>
                <input type="text" value={values.street} onChange={(e) => set('street', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Ciudad</label>
                <input type="text" value={values.city} onChange={(e) => set('city', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Código postal</label>
                <input type="text" value={values.zip} onChange={(e) => set('zip', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Rol comercial</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>Rango cliente</label>
                <input type="number" min="0" value={values.customer_rank} onChange={(e) => set('customer_rank', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Rango proveedor</label>
                <input type="number" min="0" value={values.supplier_rank} onChange={(e) => set('supplier_rank', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
          </div>

          <div className={SECTION_CLS}>
            <p className={SECTION_TITLE_CLS}>Notas internas</p>
            <textarea rows={3} value={values.comment} onChange={(e) => set('comment', e.target.value)} className={INPUT_CLS} />
          </div>

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
              {submitting ? 'Guardando...' : 'Guardar cambios'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
