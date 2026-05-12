/**
 * Panel principal de la integración WordPress / WooCommerce.
 * Muestra el estado de conexión y los módulos disponibles como tabs internos.
 *
 * @author Carlos Vico
 */
import { useEffect, useState } from 'react'
import { getWordPressStatus } from '@/api/client'
import type { IntegrationStatus } from '@/types/dolibarr'
import WordPressProducts from './WordPressProducts'
import WordPressCategories from './WordPressCategories'
import WordPressOrders from './WordPressOrders'
import WordPressCustomers from './WordPressCustomers'
import WordPressMedia from './WordPressMedia'
import WordPressConfig from './WordPressConfig'

type WordPressTab =
  | 'productos'
  | 'categorias'
  | 'pedidos'
  | 'clientes'
  | 'media'
  | 'config'

interface Props {
  className?: string
}

export default function WordPressPanel({ className = '' }: Props) {
  const [tab, setTab] = useState<WordPressTab>('productos')
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStatus = async () => {
    try {
      setLoading(true)
      const st = await getWordPressStatus()
      setStatus(st)
    } catch (err) {
      console.error('Error loading WordPress status:', err)
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
      const st = await getWordPressStatus()
      setStatus(st)
      if (st.configured) {
        setTab('productos')
      }
    } catch (err) {
      console.error('Error reloading WordPress status:', err)
    }
  }

  if (!status && loading) {
    return (
      <div className={`p-6 ${className}`}>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
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
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">WordPress / WooCommerce</h2>
          {configured && (
            <div className="flex items-center gap-2">
              {healthIcon}
              <span className="text-sm text-gray-600">{healthText}</span>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 overflow-x-auto">
          {(
            [
              { id: 'productos', label: 'Productos' },
              { id: 'categorias', label: 'Categorías' },
              { id: 'pedidos', label: 'Pedidos' },
              { id: 'clientes', label: 'Clientes' },
              { id: 'media', label: 'Media' },
              { id: 'config', label: 'Configuración' },
            ] as Array<{ id: WordPressTab; label: string }>
          ).map((t) => {
            const disabled = !configured && t.id !== 'config'
            return (
              <button
                key={t.id}
                onClick={() => !disabled && setTab(t.id)}
                className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
                  tab === t.id
                    ? 'text-purple-600 border-b-2 border-purple-600'
                    : 'text-gray-700 hover:text-gray-900'
                } ${disabled ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
              >
                {t.label}
              </button>
            )
          })}
        </div>

        {/* Content */}
        <div className="p-6">
          {tab === 'productos' && <WordPressProducts />}
          {tab === 'categorias' && <WordPressCategories />}
          {tab === 'pedidos' && <WordPressOrders />}
          {tab === 'clientes' && <WordPressCustomers />}
          {tab === 'media' && <WordPressMedia />}
          {/* Config stays mounted to preserve form state across tab switches */}
          <div className={tab === 'config' ? '' : 'hidden'}>
            <WordPressConfig onSaved={handleConfigSaved} />
          </div>
        </div>
      </div>
    </div>
  )
}
