/**
 * Panel de configuración de Dolibarr.
 * Permite guardar URL y API Key en la interfaz gráfica.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import { apiClient } from '@/api/client'

interface DolibarrConfigData {
  url: string
  api_key: string
  configured: boolean
}

interface Props {
  className?: string
  onSaved?: () => void
}

export default function DolibarrConfig({ className = '', onSaved }: Props) {
  const [url, setUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState({ type: '', text: '' })

  // Cargar config guardada
  useEffect(() => {
    ;(async () => {
      try {
        setLoading(true)
        const res = await apiClient.get<DolibarrConfigData>('/dolibarr/config')
        if (res.data) {
          setUrl(res.data.url || '')
          setApiKey(res.data.api_key || '')
        }
      } catch (err) {
        console.error('Error cargando config Dolibarr:', err)
        setMessage({ type: 'error', text: 'Error al cargar configuración' })
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const handleSave = async () => {
    if (!url.trim() || !apiKey.trim()) {
      setMessage({ type: 'error', text: 'URL y API Key son requeridas' })
      return
    }

    try {
      setSaving(true)
      const res = await apiClient.post<DolibarrConfigData>('/dolibarr/config', {
        url: url.trim(),
        api_key: apiKey.trim(),
      })

      if (res.data) {
        setMessage({ type: 'success', text: 'Configuración guardada correctamente ✓' })
        onSaved?.()
      }
    } catch (err) {
      console.error('Error guardando config:', err)
      setMessage({ type: 'error', text: 'Error al guardar configuración' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className={`p-6 ${className}`}>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      </div>
    )
  }

  return (
    <div className={`p-6 ${className}`}>
      <div className="max-w-xl">
        <h3 className="text-lg font-semibold text-gray-900 mb-6">Configuración Dolibarr</h3>

        {/* Advertencia informativa */}
        <div className="bg-blue-50 border-l-4 border-blue-400 p-4 mb-6 rounded">
          <p className="text-sm text-blue-800">
            Ingresa la URL base de tu instancia Dolibarr y la API Key. Estos datos se guardan
            localmente y se utilizan para conectar con Dolibarr.
          </p>
        </div>

        {/* Formulario */}
        <div className="space-y-4">
          {/* URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              URL de Dolibarr
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://mi-dolibarr.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Ejemplo: https://dolibarr.ejemplo.com (sin barra final)
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Pega tu API Key aquí"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Obtén la API Key en: Inicio → Configuración → API/REST → Generar clave
            </p>
          </div>

          {/* Mensaje de estado */}
          {message.text && (
            <div
              className={`p-3 rounded text-sm ${
                message.type === 'success'
                  ? 'bg-green-50 text-green-800 border border-green-200'
                  : 'bg-red-50 text-red-800 border border-red-200'
              }`}
            >
              {message.text}
            </div>
          )}

          {/* Botón guardar */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm transition-colors"
            >
              {saving ? 'Guardando...' : 'Guardar Configuración'}
            </button>
          </div>
        </div>

        {/* Info de ayuda */}
        <div className="mt-8 pt-6 border-t border-gray-200">
          <h4 className="text-sm font-semibold text-gray-900 mb-3">¿Cómo obtener las credenciales?</h4>
          <ol className="text-sm text-gray-600 space-y-2">
            <li>1. Accede a tu instancia Dolibarr como administrador</li>
            <li>2. Navega a Inicio → Configuración → API/REST</li>
            <li>3. En la sección "Gestión de tokens", pulsa "Crear una nueva clave API"</li>
            <li>4. Copia la clave generada y pégala aquí</li>
            <li>5. La URL es simplemente tu dominio de Dolibarr (ej: https://mi-dolibarr.com)</li>
          </ol>
        </div>
      </div>
    </div>
  )
}
