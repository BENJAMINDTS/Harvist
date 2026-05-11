/**
 * Panel de gestión de categorías WooCommerce con árbol jerárquico.
 *
 * @author Carlos Vico
 */
import { useEffect, useState } from 'react'
import {
  listWordPressCategories,
  createWordPressCategory,
  deleteWordPressCategory,
} from '@/api/client'
import type { WooCategory } from '@/types/wordpress'

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm'

function CategoryRow({
  cat,
  depth,
  onDelete,
}: {
  cat: WooCategory
  depth: number
  onDelete: (id: number, name: string) => void
}) {
  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-6 py-4 text-sm text-gray-500">{cat.id}</td>
        <td className="px-6 py-4 text-sm text-gray-900">
          <span style={{ paddingLeft: `${depth * 20}px` }}>
            {depth > 0 && <span className="text-gray-400 mr-1">└</span>}
            {cat.name}
          </span>
        </td>
        <td className="px-6 py-4 text-sm font-mono text-gray-500">{cat.slug}</td>
        <td className="px-6 py-4 text-sm text-gray-600">{cat.count}</td>
        <td className="px-6 py-4 text-sm">
          <button
            onClick={() => onDelete(cat.id, cat.name)}
            className="text-red-600 hover:text-red-800 text-xs font-medium"
          >
            Eliminar
          </button>
        </td>
      </tr>
      {cat.children?.map((child) => (
        <CategoryRow key={child.id} cat={child} depth={depth + 1} onDelete={onDelete} />
      ))}
    </>
  )
}

function buildTree(cats: WooCategory[]): WooCategory[] {
  const byId: Record<number, WooCategory> = {}
  cats.forEach((c) => { byId[c.id] = { ...c, children: [] } })
  const roots: WooCategory[] = []
  Object.values(byId).forEach((c) => {
    if (c.parent && byId[c.parent]) {
      byId[c.parent].children!.push(c)
    } else {
      roots.push(c)
    }
  })
  return roots
}

export default function WordPressCategories() {
  const [categories, setCategories] = useState<WooCategory[]>([])
  const [tree, setTree] = useState<WooCategory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formName, setFormName] = useState('')
  const [formParent, setFormParent] = useState<number>(0)
  const [formDesc, setFormDesc] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'tree' | 'flat'>('tree')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const items = await listWordPressCategories()
      setCategories(items)
      setTree(buildTree(items))
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando categorías.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`¿Eliminar categoría "${name}"?`)) return
    try {
      await deleteWordPressCategory(id)
      const updated = categories.filter((c) => c.id !== id)
      setCategories(updated)
      setTree(buildTree(updated))
    } catch (err: unknown) {
      alert((err as { message?: string })?.message ?? 'Error eliminando categoría.')
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName) { setFormError('El nombre es obligatorio.'); return }
    setSaving(true); setFormError(null)
    try {
      const created = await createWordPressCategory({
        name: formName,
        parent: formParent,
        description: formDesc,
      })
      const newList = [...categories, created]
      setCategories(newList)
      setTree(buildTree(newList))
      setShowForm(false)
      setFormName(''); setFormParent(0); setFormDesc('')
    } catch (err: unknown) {
      setFormError((err as { message?: string })?.message ?? 'Error creando categoría.')
    } finally {
      setSaving(false)
    }
  }

  const flatRows = viewMode === 'flat' ? categories : []

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <div className="flex border border-gray-300 rounded-lg overflow-hidden">
          {(['tree', 'flat'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              className={`px-3 py-1.5 text-sm font-medium ${viewMode === m ? 'bg-purple-600 text-white' : 'text-gray-700 hover:bg-gray-50'}`}
            >
              {m === 'tree' ? 'Árbol' : 'Plano'}
            </button>
          ))}
        </div>
        <button onClick={load} disabled={loading} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">
          ↻ Refrescar
        </button>
        <button onClick={() => setShowForm(true)} className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium">
          + Nueva categoría
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
              {['ID', 'Nombre', 'Slug', 'Productos', 'Acciones'].map((h) => (
                <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">Cargando categorías...</td></tr>
            ) : viewMode === 'tree' ? (
              tree.length === 0
                ? <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">Sin categorías.</td></tr>
                : tree.map((c) => <CategoryRow key={c.id} cat={c} depth={0} onDelete={handleDelete} />)
            ) : (
              flatRows.length === 0
                ? <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">Sin categorías.</td></tr>
                : flatRows.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-500">{c.id}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{c.name}</td>
                    <td className="px-6 py-4 text-sm font-mono text-gray-500">{c.slug}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{c.count}</td>
                    <td className="px-6 py-4 text-sm">
                      <button onClick={() => handleDelete(c.id, c.name)} className="text-red-600 hover:text-red-800 text-xs font-medium">Eliminar</button>
                    </td>
                  </tr>
                ))
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Nueva categoría</h3>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>
            <div className="px-6 py-4">
              <form onSubmit={handleCreate} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Nombre *</label>
                  <input value={formName} onChange={(e) => setFormName(e.target.value)} className={INPUT_CLS} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Categoría padre</label>
                  <select value={formParent} onChange={(e) => setFormParent(Number(e.target.value))} className={INPUT_CLS}>
                    <option value={0}>Sin padre (raíz)</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Descripción</label>
                  <textarea rows={2} value={formDesc} onChange={(e) => setFormDesc(e.target.value)} className={`${INPUT_CLS} resize-none`} />
                </div>
              </form>
            </div>
            <div className="px-6 py-4 border-t border-gray-200 space-y-3">
              {formError && <p className="text-sm text-red-600">{formError}</p>}
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowForm(false)} className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">Cancelar</button>
                <button onClick={handleCreate} disabled={saving} className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-medium">{saving ? 'Creando...' : 'Crear'}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
