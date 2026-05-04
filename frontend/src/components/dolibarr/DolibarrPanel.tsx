/**
 * Panel principal de la integración Dolibarr.
 * Muestra el estado de conexión y los módulos disponibles como tabs internos.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { getDolibarrStatus } from '@/api/client'
import { type IntegrationStatus } from '@/types/dolibarr'
import DolibarrProducts from './DolibarrProducts'
import DolibarrThirdparties from './DolibarrThirdparties'
import DolibarrOrders from './DolibarrOrders'
import DolibarrInvoices from './DolibarrInvoices'
import DolibarrStocks from './DolibarrStocks'
import DolibarrConfig from './DolibarrConfig'

type DolibarrTab = 'productos' | 'terceros' | 'pedidos' | 'facturas' | 'stock' | 'config'

interface Props {
  className?: string
}

export default function DolibarrPanel({ className = '' }: Props) {
  const [tab, setTab] = useState<DolibarrTab>('productos')
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        setLoading(true)
        const st = await getDolibarrStatus()
        setStatus(st)
      } catch (err) {
        console.error('Error loading Dolibarr status:', err)
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
            <svg
              className="h-5 w-5 text-orange-400 mt-0.5 mr-3 flex-shrink-0"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
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
      <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
          clipRule="evenodd"
        />
      </svg>
    ) : status.healthy === false ? (
      <svg className="h-4 w-4 text-red-500" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
          clipRule="evenodd"
        />
      </svg>
    ) : (
      <svg className="h-4 w-4 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
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
        <div className="flex border-b border-gray-200 overflow-x-auto">
          {(
            [
              { id: 'productos', label: 'Productos' },
              { id: 'terceros', label: 'Terceros' },
              { id: 'pedidos', label: 'Pedidos' },
              { id: 'facturas', label: 'Facturas' },
              { id: 'stock', label: 'Stock' },
              { id: 'config', label: 'Configuración' },
            ] as Array<{ id: DolibarrTab; label: string }>
          ).map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
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
          {tab === 'config' && <DolibarrConfig />}
        </div>
      </div>
    </div>
  )
}
