/**
 * Panel principal de la integración Dolibarr.
 * Muestra el estado de conexión y los módulos disponibles como tabs internos.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle, Circle } from 'lucide-react'
import { getDolibarrStatus } from '@/api/client'
import { type IntegrationStatus } from '@/types/dolibarr'
import DolibarrProducts from './DolibarrProducts'
import DolibarrThirdparties from './DolibarrThirdparties'
import DolibarrOrders from './DolibarrOrders'
import DolibarrInvoices from './DolibarrInvoices'
import DolibarrStocks from './DolibarrStocks'

type DolibarrTab = 'productos' | 'terceros' | 'pedidos' | 'facturas' | 'stock'

interface Props {
  className?: string
}

export default function DolibarrPanel({ className = '' }: Props) {
  const [tab, setTab] = useState<DolibarrTab>('productos')
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        setLoading(true)
        const st = await getDolibarrStatus()
        setStatus(st)
        if (!st.configured) setError(null)
      } catch (err) {
        setError((err as Error).message ?? 'Error al cargar estado')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  if (!status && loading) {
    return (
      <div className={`p-6 ${className}`}>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      </div>
    )
  }

  if (!status?.configured) {
    return (
      <div className={`p-6 ${className}`}>
        <div className="bg-orange-50 border-l-4 border-orange-400 p-4 rounded">
          <div className="flex items-start">
            <AlertCircle className="h-5 w-5 text-orange-400 mt-0.5 mr-3 flex-shrink-0" />
            <div>
              <h3 className="text-sm font-medium text-orange-800">
                Dolibarr no está configurado
              </h3>
              <p className="text-sm text-orange-700 mt-1">
                Añade DOLIBARR_URL y DOLIBARR_API_KEY a tu archivo .env y reinicia el
                servidor.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const healthIcon =
    status.healthy === true ? (
      <CheckCircle className="h-4 w-4 text-green-500" />
    ) : status.healthy === false ? (
      <AlertCircle className="h-4 w-4 text-red-500" />
    ) : (
      <Circle className="h-4 w-4 text-gray-400" />
    )

  const healthText =
    status.healthy === true
      ? 'Conectado'
      : status.healthy === false
        ? 'Sin conexión'
        : 'Comprobando...'

  return (
    <div className={`${className}`}>
      <div className="bg-white rounded-lg shadow">
        {/* Header con badge de estado */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Dolibarr</h2>
          <div className="flex items-center gap-2">
            {healthIcon}
            <span className="text-sm text-gray-600">{healthText}</span>
          </div>
        </div>

        {/* Tabs internos */}
        <div className="flex border-b border-gray-200">
          {(
            [
              { id: 'productos', label: 'Productos' },
              { id: 'terceros', label: 'Terceros' },
              { id: 'pedidos', label: 'Pedidos' },
              { id: 'facturas', label: 'Facturas' },
              { id: 'stock', label: 'Stock' },
            ] as Array<{ id: DolibarrTab; label: string }>
          ).map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-700 hover:text-gray-900'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Contenido del tab */}
        <div className="p-6">
          {tab === 'productos' && <DolibarrProducts />}
          {tab === 'terceros' && <DolibarrThirdparties />}
          {tab === 'pedidos' && <DolibarrOrders />}
          {tab === 'facturas' && <DolibarrInvoices />}
          {tab === 'stock' && <DolibarrStocks />}
        </div>
      </div>
    </div>
  )
}
