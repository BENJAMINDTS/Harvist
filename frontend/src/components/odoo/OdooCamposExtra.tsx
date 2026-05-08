/**
 * Módulo de gestión de campos extra (Properties) de productos Odoo 17.
 *
 * Permite seleccionar una categoría y gestionar sus definiciones de
 * campos extra: crear, editar etiqueta/opciones y eliminar.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import {
  listOdooCategories,
  getOdooCategoryProperties,
  addOdooCategoryProperty,
  updateOdooCategoryProperty,
  deleteOdooCategoryProperty,
} from '@/api/client'
import type { OdooCategory, OdooPropertyDefinition, OdooPropertyType } from '@/types/odoo'

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'

const PROPERTY_TYPES: Array<{ value: OdooPropertyType; label: string }> = [
  { value: 'char', label: 'Texto' },
  { value: 'integer', label: 'Entero' },
  { value: 'float', label: 'Decimal' },
  { value: 'boolean', label: 'Sí/No' },
  { value: 'date', label: 'Fecha' },
  { value: 'many2one', label: 'Relación' },
  { value: 'tags', label: 'Etiquetas' },
]

const TYPE_BADGE: Record<OdooPropertyType, string> = {
  char: 'bg-blue-100 text-blue-700',
  integer: 'bg-purple-100 text-purple-700',
  float: 'bg-indigo-100 text-indigo-700',
  boolean: 'bg-yellow-100 text-yellow-700',
  date: 'bg-green-100 text-green-700',
  many2one: 'bg-orange-100 text-orange-700',
  tags: 'bg-pink-100 text-pink-700',
}

export default function OdooCamposExtra() {
  const [categories, setCategories] = useState<OdooCategory[]>([])
  const [selectedCatId, setSelectedCatId] = useState<number | null>(null)
  const [definitions, setDefinitions] = useState<OdooPropertyDefinition[]>([])
  const [loadingCats, setLoadingCats] = useState(true)
  const [loadingDefs, setLoadingDefs] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)

  useEffect(() => {
    listOdooCategories(500, 0)
      .then((r) => setCategories(r.items))
      .catch((err) => setError((err as Error).message ?? 'Error cargando categorías'))
      .finally(() => setLoadingCats(false))
  }, [])

  const loadDefinitions = async (catId: number) => {
    setLoadingDefs(true)
    setError(null)
    try {
      const defs = await getOdooCategoryProperties(catId)
      setDefinitions(Array.isArray(defs) ? defs : [])
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando campos extra')
    } finally {
      setLoadingDefs(false)
    }
  }

  const handleCategoryChange = (catId: number | null) => {
    setSelectedCatId(catId)
    setDefinitions([])
    setShowAddForm(false)
    if (catId) loadDefinitions(catId)
  }

  const handleAdded = () => {
    setShowAddForm(false)
    if (selectedCatId) loadDefinitions(selectedCatId)
  }

  const handleDeleted = () => {
    if (selectedCatId) loadDefinitions(selectedCatId)
  }

  const handleUpdated = (updated: OdooPropertyDefinition) => {
    setDefinitions((prev) => prev.map((d) => (d.name === updated.name ? updated : d)))
  }

  return (
    <div className="space-y-6">
      {/* Selector de categoría */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <label className={LABEL_CLS}>Categoría de producto</label>
        {loadingCats ? (
          <p className="text-sm text-gray-500">Cargando categorías...</p>
        ) : (
          <select
            value={selectedCatId ?? ''}
            onChange={(e) => handleCategoryChange(e.target.value ? Number(e.target.value) : null)}
            className={INPUT_CLS}
          >
            <option value="">— Selecciona una categoría —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.complete_name || c.name}
              </option>
            ))}
          </select>
        )}
        <p className="mt-1 text-xs text-gray-400">
          Los campos extra definidos aquí aparecen en todos los productos de esa categoría.
          La categoría "All" aplica a todos los productos.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Panel de definiciones */}
      {selectedCatId && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">
              Campos extra definidos
              {!loadingDefs && (
                <span className="ml-2 text-gray-400 font-normal">({definitions.length})</span>
              )}
            </h3>
            <button
              onClick={() => setShowAddForm(true)}
              disabled={showAddForm}
              className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              + Nuevo campo
            </button>
          </div>

          {showAddForm && (
            <AddPropertyForm
              categoryId={selectedCatId}
              onSuccess={handleAdded}
              onCancel={() => setShowAddForm(false)}
            />
          )}

          {loadingDefs ? (
            <p className="text-sm text-gray-500">Cargando...</p>
          ) : !definitions || definitions.length === 0 ? (
            <div className="border-2 border-dashed border-gray-200 rounded-lg p-8 text-center">
              <p className="text-sm text-gray-400">Esta categoría no tiene campos extra.</p>
              <button
                onClick={() => setShowAddForm(true)}
                className="mt-2 text-sm text-blue-600 hover:text-blue-800 font-medium"
              >
                Añadir el primero
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Tipo</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Etiqueta</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Identificador</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Kanban</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {definitions.map((def) => (
                    <PropertyRow
                      key={def.name}
                      definition={def}
                      categoryId={selectedCatId}
                      onUpdated={handleUpdated}
                      onDeleted={handleDeleted}
                      onError={setError}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Fila editable de definición ──────────────────────────────────────────────

interface PropertyRowProps {
  definition: OdooPropertyDefinition
  categoryId: number
  onUpdated: (def: OdooPropertyDefinition) => void
  onDeleted: () => void
  onError: (msg: string) => void
}

function PropertyRow({ definition, categoryId, onUpdated, onDeleted, onError }: PropertyRowProps) {
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(definition.string)
  const [viewInCards, setViewInCards] = useState(definition.view_in_cards)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const typeInfo = PROPERTY_TYPES.find((t) => t.value === definition.type)

  const handleSave = async () => {
    if (!label.trim()) return
    setSaving(true)
    try {
      const updated = await updateOdooCategoryProperty(categoryId, definition.name, {
        string: label.trim(),
        view_in_cards: viewInCards,
      })
      onUpdated(updated)
      setEditing(false)
    } catch (err) {
      onError((err as Error).message ?? 'Error actualizando campo')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm(`¿Eliminar el campo "${definition.string}"? Se perderán los valores en todos los productos de esta categoría.`)) return
    setDeleting(true)
    try {
      await deleteOdooCategoryProperty(categoryId, definition.name)
      onDeleted()
    } catch (err) {
      onError((err as Error).message ?? 'Error eliminando campo')
      setDeleting(false)
    }
  }

  const handleCancel = () => {
    setLabel(definition.string)
    setViewInCards(definition.view_in_cards)
    setEditing(false)
  }

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3">
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[definition.type] ?? 'bg-gray-100 text-gray-700'}`}>
          {typeInfo?.label ?? definition.type}
        </span>
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="px-2 py-1 border border-gray-300 rounded text-sm w-48 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            autoFocus
          />
        ) : (
          <span className="text-sm font-medium text-gray-900">{definition.string}</span>
        )}
      </td>
      <td className="px-4 py-3">
        <code className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded font-mono">
          {definition.name}
        </code>
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <input
            type="checkbox"
            checked={viewInCards}
            onChange={(e) => setViewInCards(e.target.checked)}
            className="rounded"
          />
        ) : (
          <span className={`text-xs ${definition.view_in_cards ? 'text-green-600' : 'text-gray-400'}`}>
            {definition.view_in_cards ? 'Sí' : 'No'}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="text-xs font-medium text-blue-600 hover:text-blue-800 disabled:opacity-50"
            >
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
            <button
              onClick={handleCancel}
              className="text-xs font-medium text-gray-500 hover:text-gray-700"
            >
              Cancelar
            </button>
          </div>
        ) : (
          <div className="flex gap-3">
            <button
              onClick={() => setEditing(true)}
              className="text-xs font-medium text-blue-600 hover:text-blue-800"
            >
              Editar
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-xs font-medium text-red-600 hover:text-red-800 disabled:opacity-50"
            >
              {deleting ? '...' : 'Eliminar'}
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

// ── Formulario para añadir nueva definición ──────────────────────────────────

interface AddPropertyFormProps {
  categoryId: number
  onSuccess: () => void
  onCancel: () => void
}

function AddPropertyForm({ categoryId, onSuccess, onCancel }: AddPropertyFormProps) {
  const [type, setType] = useState<OdooPropertyType>('char')
  const [label, setLabel] = useState('')
  const [viewInCards, setViewInCards] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!label.trim()) {
      setError('La etiqueta es obligatoria.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await addOdooCategoryProperty(categoryId, {
        type,
        string: label.trim(),
        default: '',
        view_in_cards: viewInCards,
      })
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error añadiendo campo extra')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="border border-green-200 bg-green-50 rounded-lg p-4 space-y-3">
      <p className="text-sm font-semibold text-green-800">Nuevo campo extra</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={LABEL_CLS}>Etiqueta <span className="text-red-500">*</span></label>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Nombre visible del campo"
            className={INPUT_CLS}
            autoFocus
          />
        </div>
        <div>
          <label className={LABEL_CLS}>Tipo de dato</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as OdooPropertyType)}
            className={INPUT_CLS}
          >
            {PROPERTY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="col-span-2 flex items-center gap-2">
          <input
            id="add-view-in-cards"
            type="checkbox"
            checked={viewInCards}
            onChange={(e) => setViewInCards(e.target.checked)}
            className="rounded"
          />
          <label htmlFor="add-view-in-cards" className="text-xs text-gray-700">
            Mostrar en vistas kanban
          </label>
        </div>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
        >
          Cancelar
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="flex-1 px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
        >
          {submitting ? 'Añadiendo...' : 'Añadir campo'}
        </button>
      </div>
    </div>
  )
}
