/**
 * Panel de configuración de Dolibarr.
 * Permite guardar URL, API Key y credenciales de BD MariaDB/MySQL
 * desde la interfaz gráfica, sin editar variables de entorno.
 *
 * @author BenjaminDTS | Carlitos6712
 */
import { useEffect, useState } from 'react'
import { apiClient } from '@/api/client'
import { getDolibarrDBConfig, saveDolibarrDBConfig } from '@/api/client'
import type { DolibarrDBConfig, DolibarrDBConfigCreate } from '@/types/dolibarr'

interface DolibarrConfigData {
  url: string
  api_key: string
  configured: boolean
}

interface Props {
  className?: string
  onSaved?: () => void
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm'
const LABEL_CLS = 'block text-sm font-medium text-gray-700 mb-1'

export default function DolibarrConfig({ className = '', onSaved }: Props) {
  // ── API config ──────────────────────────────────────────────────────────
  const [url, setUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [apiMessage, setApiMessage] = useState({ type: '', text: '' })

  // ── DB config ───────────────────────────────────────────────────────────
  const [dbConfig, setDbConfig] = useState<DolibarrDBConfigCreate>({
    host: '',
    port: 3306,
    db_name: '',
    user: '',
    password: '',
    prefix: 'llx_',
  })
  const [dbConfigured, setDbConfigured] = useState(false)
  const [savingDb, setSavingDb] = useState(false)
  const [dbMessage, setDbMessage] = useState({ type: '', text: '' })
  const [showDbSection, setShowDbSection] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        setLoading(true)
        const [apiRes, dbRes] = await Promise.allSettled([
          apiClient.get<DolibarrConfigData>('/dolibarr/config'),
          getDolibarrDBConfig(),
        ])

        if (apiRes.status === 'fulfilled' && apiRes.value.data) {
          setUrl(apiRes.value.data.url || '')
          setApiKey(apiRes.value.data.api_key || '')
        }

        if (dbRes.status === 'fulfilled') {
          const db: DolibarrDBConfig = dbRes.value
          setDbConfigured(db.configured)
          if (db.configured) {
            setDbConfig({
              host: db.host,
              port: db.port,
              db_name: db.db_name,
              user: db.user,
              password: db.password,
              prefix: db.prefix,
            })
          }
        }
      } catch (err) {
        console.error('Error cargando config Dolibarr:', err)
        setApiMessage({ type: 'error', text: 'Error al cargar configuración' })
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const handleSaveApi = async () => {
    if (!url.trim() || !apiKey.trim()) {
      setApiMessage({ type: 'error', text: 'URL y API Key son requeridas' })
      return
    }
    try {
      setSaving(true)
      await apiClient.post<DolibarrConfigData>('/dolibarr/config', {
        url: url.trim(),
        api_key: apiKey.trim(),
      })
      setApiMessage({ type: 'success', text: 'Configuración guardada correctamente ✓' })
      onSaved?.()
    } catch (err) {
      console.error('Error guardando config:', err)
      setApiMessage({ type: 'error', text: 'Error al guardar configuración' })
    } finally {
      setSaving(false)
    }
  }

  const handleSaveDB = async () => {
    if (!dbConfig.host.trim() || !dbConfig.db_name.trim() || !dbConfig.user.trim()) {
      setDbMessage({ type: 'error', text: 'Host, nombre de BD y usuario son obligatorios.' })
      return
    }
    try {
      setSavingDb(true)
      setDbMessage({ type: '', text: '' })
      await saveDolibarrDBConfig(dbConfig)
      setDbConfigured(true)
      setDbMessage({
        type: 'success',
        text: 'Credenciales de BD guardadas ✓ — Harvist usará acceso directo a MariaDB como fallback.',
      })
    } catch (err) {
      console.error('Error guardando config BD:', err)
      setDbMessage({
        type: 'error',
        text: (err as Error).message ?? 'Error al guardar credenciales de BD',
      })
    } finally {
      setSavingDb(false)
    }
  }

  const setDb = <K extends keyof DolibarrDBConfigCreate>(
    key: K,
    value: DolibarrDBConfigCreate[K],
  ) => setDbConfig((prev) => ({ ...prev, [key]: value }))

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
      <div className="max-w-xl space-y-10">

        {/* ── Sección API ──────────────────────────────────────────────── */}
        <section>
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Conexión API REST</h3>

          <div className="bg-blue-50 border-l-4 border-blue-400 p-4 mb-5 rounded text-sm text-blue-800">
            URL base de tu instancia Dolibarr y API Key para conectar via REST.
          </div>

          <div className="space-y-4">
            <div>
              <label className={LABEL_CLS}>URL de Dolibarr</label>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://mi-dolibarr.com"
                className={INPUT_CLS}
              />
              <p className="text-xs text-gray-500 mt-1">Sin barra final</p>
            </div>

            <div>
              <label className={LABEL_CLS}>API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Pega tu API Key aquí"
                className={INPUT_CLS}
              />
              <p className="text-xs text-gray-500 mt-1">
                Inicio → Configuración → API/REST → Generar clave
              </p>
            </div>

            {apiMessage.text && (
              <div
                className={`p-3 rounded text-sm ${
                  apiMessage.type === 'success'
                    ? 'bg-green-50 text-green-800 border border-green-200'
                    : 'bg-red-50 text-red-800 border border-red-200'
                }`}
              >
                {apiMessage.text}
              </div>
            )}

            <button
              onClick={handleSaveApi}
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 font-medium text-sm transition-colors"
            >
              {saving ? 'Guardando...' : 'Guardar configuración API'}
            </button>
          </div>
        </section>

        {/* ── Sección BD directa ───────────────────────────────────────── */}
        <section>
          <button
            onClick={() => setShowDbSection((v) => !v)}
            className="flex items-center gap-2 w-full text-left"
          >
            <h3 className="text-lg font-semibold text-gray-900">
              Acceso directo a BD (MariaDB / MySQL)
            </h3>
            {dbConfigured && (
              <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full font-medium">
                Configurado
              </span>
            )}
            <svg
              className={`ml-auto h-5 w-5 text-gray-400 transition-transform ${showDbSection ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showDbSection && (
            <div className="mt-4 space-y-4">
              <div className="bg-amber-50 border-l-4 border-amber-400 p-4 rounded text-sm text-amber-800 space-y-1">
                <p className="font-medium">¿Para qué sirve esto?</p>
                <p>
                  Algunas versiones de Dolibarr no exponen el endpoint REST de campos extra.
                  Con acceso directo a MariaDB, Harvist puede crear y listar campos extra
                  sin depender de la API. Solo se usa como <strong>fallback</strong> cuando
                  la API devuelve error.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={LABEL_CLS}>
                    Host <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={dbConfig.host}
                    onChange={(e) => setDb('host', e.target.value)}
                    placeholder="localhost o IP del servidor"
                    className={INPUT_CLS}
                  />
                </div>
                <div>
                  <label className={LABEL_CLS}>Puerto</label>
                  <input
                    type="number"
                    value={dbConfig.port}
                    onChange={(e) => setDb('port', Number(e.target.value))}
                    min={1}
                    max={65535}
                    className={INPUT_CLS}
                  />
                </div>
              </div>

              <div>
                <label className={LABEL_CLS}>
                  Nombre de la BD <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={dbConfig.db_name}
                  onChange={(e) => setDb('db_name', e.target.value)}
                  placeholder="dolibarr"
                  className={INPUT_CLS}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={LABEL_CLS}>
                    Usuario <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={dbConfig.user}
                    onChange={(e) => setDb('user', e.target.value)}
                    placeholder="dolibarr_user"
                    className={INPUT_CLS}
                  />
                </div>
                <div>
                  <label className={LABEL_CLS}>Contraseña</label>
                  <input
                    type="password"
                    value={dbConfig.password}
                    onChange={(e) => setDb('password', e.target.value)}
                    placeholder="••••••••"
                    className={INPUT_CLS}
                  />
                </div>
              </div>

              <div>
                <label className={LABEL_CLS}>Prefijo de tablas</label>
                <input
                  type="text"
                  value={dbConfig.prefix}
                  onChange={(e) => setDb('prefix', e.target.value)}
                  placeholder="llx_"
                  className={INPUT_CLS}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Por defecto <code className="bg-gray-100 px-1 rounded">llx_</code> en todas las instalaciones estándar de Dolibarr
                </p>
              </div>

              {dbMessage.text && (
                <div
                  className={`p-3 rounded text-sm ${
                    dbMessage.type === 'success'
                      ? 'bg-green-50 text-green-800 border border-green-200'
                      : 'bg-red-50 text-red-800 border border-red-200'
                  }`}
                >
                  {dbMessage.text}
                </div>
              )}

              <button
                onClick={handleSaveDB}
                disabled={savingDb}
                className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 font-medium text-sm transition-colors"
              >
                {savingDb ? 'Guardando...' : 'Guardar credenciales BD'}
              </button>
            </div>
          )}
        </section>

        {/* ── Ayuda ────────────────────────────────────────────────────── */}
        <section className="pt-4 border-t border-gray-200">
          <h4 className="text-sm font-semibold text-gray-900 mb-3">¿Cómo obtener las credenciales API?</h4>
          <ol className="text-sm text-gray-600 space-y-1">
            <li>1. Accede a tu instancia Dolibarr como administrador</li>
            <li>2. Navega a Inicio → Configuración → API/REST</li>
            <li>3. En "Gestión de tokens", pulsa "Crear una nueva clave API"</li>
            <li>4. Copia la clave generada y pégala aquí</li>
          </ol>
        </section>

      </div>
    </div>
  )
}
