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
import DolibarrExtraFields from './DolibarrExtraFields'

type DolibarrTab = 'productos' | 'terceros' | 'pedidos' | 'facturas' | 'stock' | 'campos-extra' | 'config'

interface Props {
  className?: string
}

export default function DolibarrPanel({ className = '' }: Props) {
  const [tab, setTab] = useState<DolibarrTab>('productos')
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStatus = async () => {
    try {
      setLoading(true)
      const st = await getDolibarrStatus()
      setStatus(st)
    } catch (err) {
      console.error('Error loading Dolibarr status:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  useEffect(() => {
    if (!loading && !status?.configured) {
      setTab('config')
    }
  }, [status, loading])

  const handleConfigSaved = async () => {
    try {
      const st = await getDolibarrStatus()
      setStatus(st)
      if (st.configured) {
        setTab('productos')
      }
    } catch (err) {
      console.error('Error reloading Dolibarr status:', err)
    }
  }

  if (!status && loading) {
    return (
      <div className={`p-6 ${className}`}>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      </div>
    )
  }

  const configured = status?.configured ?? false

  const healthIcon =
    status?.healthy === true ? (
      <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
          clipRule="evenodd"
        />
      </svg>
    ) : status?.healthy === false ? (
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
    status?.healthy === true
      ? 'Conectado'
      : status?.healthy === false
        ? 'Sin conexión'
        : 'Comprobando...'

  return (
    <div className={`${className}`}>
      <div className="bg-white rounded-lg shadow">
        {/* Header con badge de estado */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Dolibarr</h2>
          {configured && (
            <div className="flex items-center gap-2">
              {healthIcon}
              <span className="text-sm text-gray-600">{healthText}</span>
            </div>
          )}
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
              { id: 'campos-extra', label: 'Campos extra' },
              { id: 'config', label: 'Configuración' },
            ] as Array<{ id: DolibarrTab; label: string }>
          ).map((t) => {
            const disabled = !configured && t.id !== 'config'
            return (
              <button
                key={t.id}
                onClick={() => !disabled && setTab(t.id)}
                className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
                  tab === t.id
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-700 hover:text-gray-900'
                } ${disabled ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
              >
                {t.label}
              </button>
            )
          })}
        </div>

        {/* Contenido del tab */}
        <div className="p-6">
          {tab === 'productos' && <DolibarrProducts />}
          {tab === 'terceros' && <DolibarrThirdparties />}
          {tab === 'pedidos' && <DolibarrOrders />}
          {tab === 'facturas' && <DolibarrInvoices />}
          {tab === 'stock' && <DolibarrStocks />}
          {tab === 'campos-extra' && <DolibarrExtraFields />}
          {tab === 'config' && <DolibarrConfig onSaved={handleConfigSaved} />}
        </div>
      </div>
    </div>
  )
}
