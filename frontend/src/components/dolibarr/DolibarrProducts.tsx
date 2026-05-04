/**
 * Módulo de gestión de productos de Dolibarr.
 * Incluye CRUD y sincronización desde job Harvist completado.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import {
  listDolibarrProducts,
  deleteDolibarrProduct,
  syncDolibarrFromJob,
} from '@/api/client'
import { type DolibarrProduct } from '@/types/dolibarr'

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
      {/* Header con acciones */}
      <div className="flex gap-4">
        <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
          + Nuevo producto
        </button>
        <button
          onClick={() => setShowSyncModal(true)}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
        >
          ↓ Sincronizar desde job
        </button>
      </div>

      {/* Mensajes de error */}
      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Tabla de productos */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Ref
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Nombre
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Precio
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Tipo
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Estado
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Acciones
              </th>
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
                    €{p.price.toFixed(2)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{p.type}</td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        p.status === 1
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {p.status === 1 ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <div className="flex gap-3">
                      <button className="text-blue-600 hover:text-blue-800 text-xs font-medium">
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

      {/* Paginación */}
      {pagination.total > 0 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>
            {pagination.offset + 1} - {Math.min(pagination.offset + pagination.limit, pagination.total)} de{' '}
            {pagination.total}
          </div>
          <div className="flex gap-2">
            <button
              disabled={pagination.offset === 0}
              onClick={() => loadProducts(pagination.limit, Math.max(0, pagination.offset - pagination.limit))}
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              disabled={!pagination.has_more}
              onClick={() => loadProducts(pagination.limit, pagination.offset + pagination.limit)}
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}

      {/* Modal de sincronización */}
      {showSyncModal && (
        <SyncFromJobModal
          onClose={() => setShowSyncModal(false)}
          onSuccess={() => {
            setShowSyncModal(false)
            loadProducts()
          }}
        />
      )}
    </div>
  )
}

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

      const created = results.filter((r) => r.action === 'created').length
      const updated = results.filter((r) => r.action === 'updated').length
      const omitted = results.filter((r) => r.error !== null).length

      setResult({ created, updated, omitted })
    } catch (err) {
      alert(`Error: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Sincronizar desde job
        </h3>

        {!result ? (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                ID del job
              </label>
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
              <span className="text-sm text-gray-700">
                Sobreescribir productos existentes
              </span>
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
                <strong>{result.created}</strong> creados · <strong>{result.updated}</strong>{' '}
                actualizados · <strong>{result.omitted}</strong> omitidos
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
