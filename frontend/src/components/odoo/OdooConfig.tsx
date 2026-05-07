/**
 * Panel de configuración de credenciales Odoo.
 *
 * @author Carlitos6712
 */
import { useEffect, useState } from 'react'
import { getOdooConfig, saveOdooConfig } from '@/api/client'
import type { IntegrationStatus } from '@/types/dolibarr'

interface Props {
  onSaved: () => void
  status: IntegrationStatus | null
}

export default function OdooConfig({ onSaved, status }: Props) {
  const [url, setUrl] = useState('')
  const [db, setDb] = useState('')
  const [user, setUser] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    getOdooConfig()
      .then((cfg) => {
        setUrl(cfg.url)
        setDb(cfg.db)
        setUser(cfg.user)
        setPassword(cfg.password)
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setError('')
    setSuccess(false)
    if (!url || !db || !user || !password) {
      setError('Todos los campos son obligatorios.')
      return
    }
    setSaving(true)
    try {
      await saveOdooConfig({ url, db, user, password })
      setSuccess(true)
      onSaved()
    } catch {
      setError('Error guardando configuración.')
    } finally {
      setSaving(false)
    }
  }

  const statusColor = status?.healthy === true
    ? 'bg-green-100 text-green-800'
    : status?.healthy === false
      ? 'bg-red-100 text-red-800'
      : 'bg-gray-100 text-gray-600'

  return (
    <div className="space-y-6">
      {status && (
        <div className={`px-4 py-3 rounded-lg text-sm font-medium ${statusColor}`}>
          {status.message || (status.healthy ? 'Odoo operativo' : 'Odoo no configurado')}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://localhost:8069"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Base de datos</label>
          <input
            type="text"
            value={db}
            onChange={(e) => setDb(e.target.value)}
            placeholder="odoo_prod"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Usuario (email)</label>
          <input
            type="email"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            placeholder="admin@empresa.com"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Contraseña</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {success && <p className="text-sm text-green-600">Configuración guardada correctamente.</p>}

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-6 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors"
      >
        {saving ? 'Guardando...' : 'Guardar configuración'}
      </button>
    </div>
  )
}
