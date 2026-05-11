/**
 * Formulario de configuración de credenciales WordPress / WooCommerce.
 *
 * @author Carlos Vico
 */
import { useState, useEffect } from 'react'
import { saveWordPressConfig, saveWordPressDBConfig, getWordPressConfig, getWordPressDBConfig } from '@/api/client'
import type { WordPressConfigRequest, WordPressDBConfigRequest } from '@/types/wordpress'

interface Props {
  onSaved: () => void
}

const INPUT_CLS =
  'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 text-sm'
const LABEL_CLS = 'block text-sm font-medium text-gray-700 mb-1'

export default function WordPressConfig({ onSaved }: Props) {
  const [url, setUrl] = useState('')
  const [consumerKey, setConsumerKey] = useState('')
  const [consumerSecret, setConsumerSecret] = useState('')
  const [apiConfigured, setApiConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [apiMessage, setApiMessage] = useState({ type: '', text: '' })

  const [dbHost, setDbHost] = useState('')
  const [dbPort, setDbPort] = useState('3306')
  const [dbName, setDbName] = useState('')
  const [dbUser, setDbUser] = useState('')
  const [dbPass, setDbPass] = useState('')
  const [dbPrefix, setDbPrefix] = useState('wp_')
  const [dbConfigured, setDbConfigured] = useState(false)
  const [savingDb, setSavingDb] = useState(false)
  const [dbMessage, setDbMessage] = useState({ type: '', text: '' })
  const [showDbSection, setShowDbSection] = useState(false)

  useEffect(() => {
    getWordPressConfig().then((cfg) => {
      if (cfg.url) setUrl(cfg.url)
      if (cfg.configured) setApiConfigured(true)
    }).catch(() => {})

    getWordPressDBConfig().then((cfg) => {
      if (cfg.host) setDbHost(cfg.host)
      if (cfg.port) setDbPort(String(cfg.port))
      if (cfg.db_name) setDbName(cfg.db_name)
      if (cfg.user) setDbUser(cfg.user)
      if (cfg.prefix) setDbPrefix(cfg.prefix)
      if (cfg.configured) {
        setDbConfigured(true)
        setShowDbSection(true)
      }
    }).catch(() => {})
  }, [])

  const handleSaveAPI = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url) {
      setApiMessage({ type: 'error', text: 'La URL de la tienda es obligatoria.' })
      return
    }
    if (!apiConfigured && (!consumerKey || !consumerSecret)) {
      setApiMessage({ type: 'error', text: 'Consumer Key y Consumer Secret son obligatorios.' })
      return
    }
    setSaving(true)
    setApiMessage({ type: '', text: '' })
    try {
      const payload: WordPressConfigRequest = { url, consumer_key: consumerKey, consumer_secret: consumerSecret }
      await saveWordPressConfig(payload)
      setApiMessage({ type: 'success', text: 'Configuración guardada correctamente ✓' })
      setApiConfigured(true)
      onSaved()
    } catch (err: unknown) {
      setApiMessage({
        type: 'error',
        text: (err as { message?: string })?.message ?? 'Error guardando configuración.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleSaveDB = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dbHost || !dbName || !dbUser) {
      setDbMessage({ type: 'error', text: 'Host, nombre de BD y usuario son obligatorios.' })
      return
    }
    setSavingDb(true)
    setDbMessage({ type: '', text: '' })
    try {
      const payload: WordPressDBConfigRequest = {
        host: dbHost,
        port: parseInt(dbPort, 10),
        db_name: dbName,
        user: dbUser,
        password: dbPass,
        prefix: dbPrefix,
      }
      await saveWordPressDBConfig(payload)
      setDbMessage({ type: 'success', text: 'Credenciales de BD guardadas ✓' })
      setDbConfigured(true)
    } catch (err: unknown) {
      setDbMessage({
        type: 'error',
        text: (err as { message?: string })?.message ?? 'Error guardando configuración de BD.',
      })
    } finally {
      setSavingDb(false)
    }
  }

  return (
    <div className="p-6">
      <div className="max-w-xl space-y-10">

        {/* ── Sección API ──────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-3 mb-4">
            <h3 className="text-lg font-semibold text-gray-900">Conexión WooCommerce API</h3>
            {apiConfigured && (
              <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded-full">Configurado</span>
            )}
          </div>

          <div className="bg-purple-50 border-l-4 border-purple-400 p-4 mb-5 rounded text-sm text-purple-800">
            URL base de tu tienda WordPress y API Key de WooCommerce REST API.
          </div>

          <form onSubmit={handleSaveAPI} className="space-y-4">
            <div>
              <label className={LABEL_CLS}>
                URL de la tienda <span className="text-red-500">*</span>
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://mi-tienda.com"
                className={INPUT_CLS}
              />
              <p className="text-xs text-gray-500 mt-1">Sin barra final</p>
            </div>

            <div>
              <label className={LABEL_CLS}>
                Consumer Key <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={consumerKey}
                onChange={(e) => setConsumerKey(e.target.value)}
                placeholder={apiConfigured ? '(guardada — deja vacío para no cambiar)' : 'ck_••••••••••••••••••••••••••••••••••••••••'}
                className={`${INPUT_CLS} font-mono`}
              />
            </div>

            <div>
              <label className={LABEL_CLS}>
                Consumer Secret <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={consumerSecret}
                onChange={(e) => setConsumerSecret(e.target.value)}
                placeholder={apiConfigured ? '(guardada — deja vacío para no cambiar)' : 'cs_••••••••••••••••••••••••••••••••••••••••'}
                className={`${INPUT_CLS} font-mono`}
              />
              <p className="text-xs text-gray-500 mt-1">
                WooCommerce → Ajustes → Avanzado → REST API → Añadir clave
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
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 font-medium text-sm transition-colors"
            >
              {saving ? 'Guardando...' : 'Guardar configuración API'}
            </button>
          </form>
        </section>

        {/* ── Sección BD directa ───────────────────────────────────────── */}
        <section>
          <button
            type="button"
            onClick={() => setShowDbSection((v) => !v)}
            className="flex items-center gap-2 w-full text-left"
          >
            <h3 className="text-lg font-semibold text-gray-900">
              Acceso directo a BD (phpMyAdmin / MySQL)
            </h3>
            {dbConfigured && (
              <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded-full">Configurado</span>
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
            <form onSubmit={handleSaveDB} className="mt-4 space-y-4">
              <div className="bg-amber-50 border-l-4 border-amber-400 p-4 rounded text-sm text-amber-800 space-y-1">
                <p className="font-medium">¿Para qué sirve esto?</p>
                <p>
                  Permite a Harvist conectarse directamente a MySQL de WordPress para ejecutar
                  consultas SQL y obtener información de la BD sin depender de la REST API.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className={LABEL_CLS}>
                    Host <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={dbHost}
                    onChange={(e) => setDbHost(e.target.value)}
                    placeholder="localhost"
                    className={INPUT_CLS}
                  />
                </div>
                <div>
                  <label className={LABEL_CLS}>Puerto</label>
                  <input
                    type="number"
                    value={dbPort}
                    onChange={(e) => setDbPort(e.target.value)}
                    placeholder="3306"
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
                  value={dbName}
                  onChange={(e) => setDbName(e.target.value)}
                  placeholder="wordpress"
                  className={INPUT_CLS}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={LABEL_CLS}>
                    Usuario <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={dbUser}
                    onChange={(e) => setDbUser(e.target.value)}
                    placeholder="root"
                    className={INPUT_CLS}
                  />
                </div>
                <div>
                  <label className={LABEL_CLS}>Contraseña</label>
                  <input
                    type="password"
                    value={dbPass}
                    onChange={(e) => setDbPass(e.target.value)}
                    placeholder="••••••••"
                    className={INPUT_CLS}
                  />
                </div>
              </div>

              <div>
                <label className={LABEL_CLS}>Prefijo de tablas</label>
                <input
                  type="text"
                  value={dbPrefix}
                  onChange={(e) => setDbPrefix(e.target.value)}
                  placeholder="wp_"
                  className={`${INPUT_CLS} font-mono`}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Por defecto <code className="bg-gray-100 px-1 rounded">wp_</code> en todas las instalaciones estándar de WordPress
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
                type="submit"
                disabled={savingDb}
                className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 font-medium text-sm transition-colors"
              >
                {savingDb ? 'Guardando...' : 'Guardar credenciales BD'}
              </button>
            </form>
          )}
        </section>

        {/* ── Ayuda ────────────────────────────────────────────────────── */}
        <section className="pt-4 border-t border-gray-200">
          <h4 className="text-sm font-semibold text-gray-900 mb-3">¿Cómo obtener la API Key?</h4>
          <ol className="text-sm text-gray-600 space-y-1">
            <li>1. Accede a tu WordPress como administrador</li>
            <li>2. Navega a WooCommerce → Ajustes → Avanzado → REST API</li>
            <li>3. Pulsa "Añadir clave" y genera una con permisos de lectura/escritura</li>
            <li>4. Copia la clave generada y pégala aquí</li>
          </ol>
        </section>

      </div>
    </div>
  )
}
