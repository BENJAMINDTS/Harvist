/**
 * Panel de gestión de categorías de producto en Odoo (product.category).
 * Árbol jerárquico con soporte para crear, editar y eliminar categorías padre e hija.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import {
  getOooCategoryTree,
  createOdooCategory,
  updateOdooCategory,
  deleteOdooCategory,
} from '@/api/client'
import type { OooCategoryTree } from '@/types/odoo'

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'
const LABEL_CLS = 'block text-xs font-medium text-gray-700 mb-1'

// ── Componente principal ───────────────────────────────────────────────────

export default function OdooCategories() {
  const [tree, setTree] = useState<OooCategoryTree[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createParentId, setCreateParentId] = useState<number | null>(null)
  const [editTarget, setEditTarget] = useState<OooCategoryTree | null>(null)

  const loadTree = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getOooCategoryTree()
      setTree(data)
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando categorías')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTree()
  }, [])

  const handleDelete = async (node: OooCategoryTree) => {
    const hasChildren = node.children.length > 0
    const msg = hasChildren
      ? `¿Eliminar "${node.name}" y todas sus subcategorías? Esta acción no se puede deshacer.`
      : `¿Eliminar la categoría "${node.name}"?`
    if (!confirm(msg)) return
    try {
      await deleteOdooCategory(node.id)
      loadTree()
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando categoría')
    }
  }

  const handleAddChild = (parentId: number) => {
    setCreateParentId(parentId)
    setShowCreateModal(true)
  }

  const handleAddRoot = () => {
    setCreateParentId(null)
    setShowCreateModal(true)
  }

  return (
    <div className="space-y-6">
      {/* Barra superior */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Categorías de producto</h3>
        <button
          onClick={handleAddRoot}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          + Nueva categoría raíz
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Árbol */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        {loading ? (
          <div className="px-6 py-10 text-center text-gray-500 text-sm">
            Cargando categorías...
          </div>
        ) : tree.length === 0 ? (
          <div className="px-6 py-10 text-center text-gray-500 text-sm">
            No hay categorías configuradas. Crea la primera arriba.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {tree.map((node) => (
              <CategoryNode
                key={node.id}
                node={node}
                depth={0}
                onAddChild={handleAddChild}
                onEdit={setEditTarget}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      {showCreateModal && (
        <CreateCategoryModal
          parentId={createParentId}
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false)
            loadTree()
          }}
        />
      )}

      {editTarget && (
        <EditCategoryModal
          category={editTarget}
          onClose={() => setEditTarget(null)}
          onSuccess={() => {
            setEditTarget(null)
            loadTree()
          }}
        />
      )}
    </div>
  )
}

// ── Nodo del árbol ─────────────────────────────────────────────────────────

interface CategoryNodeProps {
  node: OooCategoryTree
  depth: number
  onAddChild: (parentId: number) => void
  onEdit: (node: OooCategoryTree) => void
  onDelete: (node: OooCategoryTree) => void
}

function CategoryNode({ node, depth, onAddChild, onEdit, onDelete }: CategoryNodeProps) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = node.children.length > 0
  const indent = depth * 24

  return (
    <>
      <div
        className="flex items-center gap-2 px-4 py-3 hover:bg-gray-50 group"
        style={{ paddingLeft: `${16 + indent}px` }}
      >
        {/* Toggle expansion */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className={`w-5 h-5 flex items-center justify-center rounded text-gray-400 hover:text-gray-600 flex-shrink-0 ${
            !hasChildren ? 'invisible' : ''
          }`}
        >
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? 'rotate-90' : ''}`}
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </button>

        {/* Icono carpeta */}
        <svg className="w-4 h-4 text-yellow-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
        </svg>

        {/* Nombre + ruta completa */}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium text-gray-900">{node.name}</span>
          {node.complete_name && node.complete_name !== node.name && (
            <span className="ml-2 text-xs text-gray-400 truncate">{node.complete_name}</span>
          )}
          {node.children.length > 0 && (
            <span className="ml-2 text-xs text-gray-300">({node.children.length})</span>
          )}
        </div>

        {/* Badge ID */}
        <span className="text-xs text-gray-400 font-mono flex-shrink-0">#{node.id}</span>

        {/* Acciones — visibles en hover */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button
            onClick={() => onAddChild(node.id)}
            title="Añadir subcategoría"
            className="px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded"
          >
            + Sub
          </button>
          <button
            onClick={() => onEdit(node)}
            title="Editar"
            className="px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded"
          >
            Editar
          </button>
          <button
            onClick={() => onDelete(node)}
            title="Eliminar"
            className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded"
          >
            Eliminar
          </button>
        </div>
      </div>

      {/* Hijos */}
      {hasChildren && expanded && (
        <>
          {node.children.map((child) => (
            <CategoryNode
              key={child.id}
              node={child}
              depth={depth + 1}
              onAddChild={onAddChild}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </>
      )}
    </>
  )
}

// ── Modal crear categoría ──────────────────────────────────────────────────

interface CreateCategoryModalProps {
  parentId: number | null
  onClose: () => void
  onSuccess: () => void
}

function CreateCategoryModal({ parentId, onClose, onSuccess }: CreateCategoryModalProps) {
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      await createOdooCategory(name.trim(), parentId ?? undefined)
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error creando categoría')
    } finally {
      setSubmitting(false)
    }
  }

  const title = parentId != null ? 'Nueva subcategoría' : 'Nueva categoría raíz'

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-md">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {parentId != null && (
            <p className="text-xs text-gray-500">
              Subcategoría de ID <span className="font-mono font-semibold">#{parentId}</span>
            </p>
          )}

          <div>
            <label className={LABEL_CLS}>
              Nombre <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej: Electrónica"
              className={INPUT_CLS}
              autoFocus
            />
          </div>
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
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Creando...' : 'Crear'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Modal editar categoría ─────────────────────────────────────────────────

interface EditCategoryModalProps {
  category: OooCategoryTree
  onClose: () => void
  onSuccess: () => void
}

function EditCategoryModal({ category, onClose, onSuccess }: EditCategoryModalProps) {
  const [name, setName] = useState(category.name)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      await updateOdooCategory(category.id, { name: name.trim() })
      onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error actualizando categoría')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-md">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Editar categoría</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <p className="text-xs text-gray-500 font-mono">ID #{category.id}</p>

          <div>
            <label className={LABEL_CLS}>
              Nombre <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLS}
              autoFocus
            />
          </div>
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
