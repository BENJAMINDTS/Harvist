/**
 * Módulo de gestión de clientes y proveedores de Dolibarr.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { listDolibarrThirdparties, deleteDolibarrThirdparty } from '@/api/client'
import { type DolibarrThirdparty, type ThirdpartyMode } from '@/types/dolibarr'

export default function DolibarrThirdparties() {
  const [thirdparties, setThirdparties] = useState<DolibarrThirdparty[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<ThirdpartyMode>('all')
  const [pagination, setPagination] = useState({
    limit: 10,
    offset: 0,
    total: 0,
    has_more: false,
  })

  const loadThirdparties = async (
    limit = 10,
    offset = 0,
    selectedMode: ThirdpartyMode = mode,
  ) => {
    try {
      setLoading(true)
      const data = await listDolibarrThirdparties(selectedMode, limit, offset)
      setThirdparties(data.items)
      setPagination({
        limit: data.limit,
        offset: data.offset,
        total: data.total,
        has_more: data.has_more,
      })
    } catch (err) {
      console.error('Error loading thirdparties:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadThirdparties()
  }, [])

  const handleModeChange = (newMode: ThirdpartyMode) => {
    setMode(newMode)
    loadThirdparties(10, 0, newMode)
  }

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar este tercero?')) return
    try {
      await deleteDolibarrThirdparty(id)
      loadThirdparties(pagination.limit, pagination.offset, mode)
    } catch (err) {
      console.error('Error deleting thirdparty:', err)
    }
  }

  const getTypeLabel = (t: DolibarrThirdparty): string => {
    if (t.client && t.supplier) return 'Cliente y Proveedor'
    if (t.client) return 'Cliente'
    if (t.supplier) return 'Proveedor'
    return 'Sin tipo'
  }

  const getTypeBadgeColor = (t: DolibarrThirdparty): string => {
    if (t.client && t.supplier) return 'bg-purple-100 text-purple-800'
    if (t.client) return 'bg-blue-100 text-blue-800'
    return 'bg-green-100 text-green-800'
  }

  return (
    <div className="space-y-6">
      {/* Filtro de modo */}
      <div className="flex gap-2">
        {(
          [
            { id: 'all' as ThirdpartyMode, label: 'Todos' },
            { id: 'customers' as ThirdpartyMode, label: 'Clientes' },
            { id: 'suppliers' as ThirdpartyMode, label: 'Proveedores' },
          ] as const
        ).map((m) => (
          <button
            key={m.id}
            onClick={() => handleModeChange(m.id)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              mode === m.id
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Tabla */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Nombre
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Tipo
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Email
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Ciudad
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  Cargando...
                </td>
              </tr>
            ) : thirdparties.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  Sin terceros
                </td>
              </tr>
            ) : (
              thirdparties.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-900">{t.name}</td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${getTypeBadgeColor(t)}`}
                    >
                      {getTypeLabel(t)}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{t.email}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{t.town}</td>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => handleDelete(t.id)}
                      className="text-red-600 hover:text-red-800"
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

      {/* Paginación */}
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
                loadThirdparties(
                  pagination.limit,
                  Math.max(0, pagination.offset - pagination.limit),
                  mode,
                )
              }
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              disabled={!pagination.has_more}
              onClick={() =>
                loadThirdparties(
                  pagination.limit,
                  pagination.offset + pagination.limit,
                  mode,
                )
              }
              className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
