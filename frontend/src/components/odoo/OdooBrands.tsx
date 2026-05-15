/**
 * Panel de gestión de marcas en Odoo.
 * Las marcas se almacenan como subcategorías (product.public.category) bajo la categoría
 * padre "Marcas", que se crea automáticamente si no existe.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { listOdooBrands, createOdooBrand, deleteOdooBrand } from '@/api/client'
import type { OdooCategory } from '@/types/odoo'

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm'

export default function OdooBrands() {
  const [brands, setBrands] = useState<OdooCategory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listOdooBrands(200, 0)
      setBrands(data.items)
    } catch (err) {
      setError((err as Error).message ?? 'Error cargando marcas')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (brand: OdooCategory) => {
    if (!confirm(`¿Eliminar la marca "${brand.name}"?`)) return
    try {
      await deleteOdooBrand(brand.id)
      load()
    } catch (err) {
      setError((err as Error).message ?? 'Error eliminando marca')
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) { setCreateError('El nombre es obligatorio.'); return }
    setCreating(true)
    setCreateError(null)
    try {
      await createOdooBrand(newName.trim())
      setNewName('')
      setShowCreate(false)
      load()
    } catch (err) {
      setCreateError((err as Error).message ?? 'Error creando marca')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Barra superior */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Marcas ({brands.length})</h3>
        <button
          onClick={() => { setShowCreate(true); setCreateError(null) }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          + Nueva marca
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-3 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Lista de marcas */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        {loading ? (
          <div className="px-6 py-10 text-center text-gray-500 text-sm">Cargando marcas...</div>
        ) : brands.length === 0 ? (
          <div className="px-6 py-10 text-center text-gray-500 text-sm">
            No hay marcas. Crea la primera arriba.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {brands.map((brand) => (
              <div
                key={brand.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 group"
              >
                <div className="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0" />
                <span className="flex-1 text-sm font-medium text-gray-900">{brand.name}</span>
                {brand.complete_name && brand.complete_name !== brand.name && (
                  <span className="text-xs text-gray-400 truncate max-w-[200px]">{brand.complete_name}</span>
                )}
                <span className="text-xs text-gray-400 font-mono flex-shrink-0">#{brand.id}</span>
                <button
                  onClick={() => handleDelete(brand)}
                  className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                >
                  Eliminar
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal crear marca */}
      {showCreate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-sm">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Nueva marca</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>
            <div className="px-6 py-4 space-y-3">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Ej: Nike"
                className={INPUT_CLS}
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />
              {createError && <p className="text-xs text-red-600">{createError}</p>}
            </div>
            <div className="px-6 py-4 border-t border-gray-200 flex gap-3">
              <button
                onClick={() => setShowCreate(false)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
              >
                Cancelar
              </button>
              <button
                onClick={handleCreate}
                disabled={creating}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
              >
                {creating ? 'Creando...' : 'Crear'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
