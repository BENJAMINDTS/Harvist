/**
 * Panel principal de la integración Odoo.
 * Muestra el estado de conexión y los módulos disponibles como tabs internos.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { getOdooStatus } from '@/api/client'
import type { IntegrationStatus } from '@/types/dolibarr'
import OdooConfig from './OdooConfig'
import OdooProducts from './OdooProducts'
import OdooPartners from './OdooPartners'
import OooPurchases from './OdooPurchases'
import OdooSales from './OdooSales'
import OdooInvoices from './OdooInvoices'
import OdooInventory from './OdooInventory'

type OdooTab = 'productos' | 'partners' | 'compras' | 'ventas' | 'facturas' | 'inventario' | 'config'

interface Props {
  className?: string
}

export default function OdooPanel({ className = '' }: Props) {
  const [tab, setTab] = useState<OdooTab>('productos')
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStatus = async () => {
    try {
      setLoading(true)
      setStatus(await getOdooStatus())
    } catch {
      // no-op
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchStatus() }, [])

  useEffect(() => {
    if (!loading && !status?.configured) setTab('config')
  }, [status, loading])

  const handleConfigSaved = async () => {
    try {
      const st = await getOdooStatus()
      setStatus(st)
      if (st.configured) setTab('productos')
    } catch { /* no-op */ }
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

  const healthIcon = status?.healthy === true
    ? <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-2" />
    : status?.healthy === false
      ? <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-2" />
      : <span className="inline-block w-2 h-2 rounded-full bg-gray-400 mr-2" />

  const tabs: { id: OdooTab; label: string; disabled?: boolean }[] = [
    { id: 'productos', label: 'Productos', disabled: !configured },
    { id: 'partners', label: 'Partners', disabled: !configured },
    { id: 'compras', label: 'Compras', disabled: !configured },
    { id: 'ventas', label: 'Ventas', disabled: !configured },
    { id: 'facturas', label: 'Facturas', disabled: !configured },
    { id: 'inventario', label: 'Inventario', disabled: !configured },
    { id: 'config', label: 'Configuración' },
  ]

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-gray-900">Odoo</h2>
          <div className="flex items-center text-sm text-gray-500">
            {healthIcon}
            {configured ? (status?.healthy ? 'Conectado' : 'Sin conexión') : 'No configurado'}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-1 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => !t.disabled && setTab(t.id)}
              disabled={t.disabled}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap
                ${tab === t.id
                  ? 'border-purple-600 text-purple-600'
                  : t.disabled
                    ? 'border-transparent text-gray-300 cursor-not-allowed'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div>
        {tab === 'config' && (
          <OdooConfig onSaved={handleConfigSaved} status={status} />
        )}
        {tab === 'productos' && configured && <OdooProducts />}
        {tab === 'partners' && configured && <OdooPartners />}
        {tab === 'compras' && configured && <OooPurchases />}
        {tab === 'ventas' && configured && <OdooSales />}
        {tab === 'facturas' && configured && <OdooInvoices />}
        {tab === 'inventario' && configured && <OdooInventory />}
      </div>
    </div>
  )
}
