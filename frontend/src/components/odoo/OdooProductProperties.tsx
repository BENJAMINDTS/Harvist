/**
 * Sección de asignación de campos extra en el modal de producto Odoo.
 *
 * Muestra los campos definidos en la categoría del producto y permite
 * editar los valores asignados a ese producto concreto.
 *
 * Para gestionar las definiciones (crear / eliminar campos) usa el
 * módulo "Campos extra" en el panel principal de Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useRef, useState } from 'react'
import { getOdooCategoryProperties, getOdooProductProperties } from '@/api/client'
import type { OdooPropertyValue, OdooPropertyType } from '@/types/odoo'

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'

const TYPE_LABELS: Record<OdooPropertyType, string> = {
  char: 'Texto',
  integer: 'Entero',
  float: 'Decimal',
  boolean: 'Sí/No',
  date: 'Fecha',
  many2one: 'Relación',
  tags: 'Etiquetas',
}

interface Props {
  /** null = create mode (no product ID yet) */
  productId: number | null
  categoryId: number | false
  /** Called in create mode whenever field values change — parent collects for post-create save */
  onPropertiesChange?: (props: OdooPropertyValue[]) => void
}

export default function OdooProductProperties({ productId, categoryId, onPropertiesChange }: Props) {
  const [properties, setProperties] = useState<OdooPropertyValue[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const catId = typeof categoryId === 'number' ? categoryId : null
  const onPropertiesChangeRef = useRef(onPropertiesChange)
  onPropertiesChangeRef.current = onPropertiesChange

  useEffect(() => {
    if (!catId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)

    if (productId === null) {
      // Create mode: load definitions from the category, no existing values
      getOdooCategoryProperties(catId)
        .then((defs) => {
          const safe = Array.isArray(defs) ? defs : []
          const asValues: OdooPropertyValue[] = safe.map((d) => ({
            name: d.name,
            type: d.type,
            string: d.string,
            value: d.default ?? null,
          }))
          setProperties(asValues)
          const map: Record<string, string> = {}
          for (const p of asValues) {
            map[p.name] = p.value == null || p.value === false ? '' : String(p.value)
          }
          setValues(map)
        })
        .catch((err) => setError((err as Error).message ?? 'Error cargando campos extra'))
        .finally(() => setLoading(false))
    } else {
      // Edit mode: load existing product property values
      getOdooProductProperties(productId, catId)
        .then((props) => {
          const safe = Array.isArray(props) ? props : []
          setProperties(safe)
          const map: Record<string, string> = {}
          for (const p of safe) {
            map[p.name] = p.value == null || p.value === false ? '' : String(p.value)
          }
          setValues(map)
        })
        .catch((err) => setError((err as Error).message ?? 'Error cargando campos extra'))
        .finally(() => setLoading(false))
    }
  }, [productId, catId])

  // Notify parent of current property values so it can include them in the main save
  useEffect(() => {
    if (!onPropertiesChangeRef.current || properties.length === 0) return
    const payload: OdooPropertyValue[] = properties.map((p) => ({
      name: p.name,
      type: p.type,
      string: p.string,
      value: coerceValue(values[p.name] ?? '', p.type),
    }))
    onPropertiesChangeRef.current(payload)
  }, [values, properties, productId])

  if (!catId) {
    return (
      <p className="text-xs text-gray-400 italic">
        Asigna una categoría al producto para ver sus campos extra.
      </p>
    )
  }

  if (loading) {
    return <p className="text-xs text-gray-500">Cargando campos extra...</p>
  }

  if (!properties || properties.length === 0) {
    return (
      <p className="text-xs text-gray-400 italic">
        Esta categoría no tiene campos extra. Créalos en el módulo "Campos extra".
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-3 rounded text-xs text-red-700">{error}</div>
      )}

      {properties.map((prop) => (
        <div key={prop.name}>
          <label className={LABEL_CLS}>
            {prop.string}
            <span className="ml-1 text-gray-400 font-normal">
              ({TYPE_LABELS[prop.type] ?? prop.type})
            </span>
          </label>
          <PropertyInput
            type={prop.type}
            value={values[prop.name] ?? ''}
            onChange={(v) => setValues((prev) => ({ ...prev, [prop.name]: v }))}
          />
        </div>
      ))}
    </div>
  )
}

// ── Input por tipo ───────────────────────────────────────────────────────────

function PropertyInput({
  type,
  value,
  onChange,
}: {
  type: OdooPropertyType
  value: string
  onChange: (v: string) => void
}) {
  if (type === 'boolean') {
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS}>
        <option value="">— Sin valor —</option>
        <option value="true">Sí</option>
        <option value="false">No</option>
      </select>
    )
  }
  if (type === 'integer') {
    return (
      <input type="number" step="1" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS} />
    )
  }
  if (type === 'float') {
    return (
      <input type="number" step="0.01" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS} />
    )
  }
  if (type === 'date') {
    return (
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS} />
    )
  }
  return (
    <input type="text" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT_CLS} />
  )
}

// ── Coerción ─────────────────────────────────────────────────────────────────

function coerceValue(
  raw: string,
  type: OdooPropertyType,
): string | number | boolean | null {
  if (raw === '' || raw == null) return false
  if (type === 'boolean') return raw === 'true'
  if (type === 'integer') return parseInt(raw, 10) || 0
  if (type === 'float') return parseFloat(raw.replace(',', '.')) || 0
  return raw
}
