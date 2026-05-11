/**
 * Panel phpMyAdmin integrado — gestión directa de la BD MySQL de WordPress.
 * Muestra tablas, info del sitio y permite ejecutar queries SELECT.
 *
 * @author Carlos Vico
 */
import { useEffect, useState } from 'react'
import {
  listWordPressDBTables,
  getWordPressSiteInfo,
  queryWordPressDB,
} from '@/api/client'
import type { DBTable, WPSiteInfo } from '@/types/wordpress'

export default function WordPressDatabase() {
  const [tables, setTables] = useState<DBTable[]>([])
  const [siteInfo, setSiteInfo] = useState<WPSiteInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'tables' | 'query' | 'info'>('tables')

  const [sql, setSql] = useState('')
  const [queryRows, setQueryRows] = useState<Record<string, unknown>[]>([])
  const [queryCount, setQueryCount] = useState<number | null>(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [queryError, setQueryError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [tbls, info] = await Promise.all([
        listWordPressDBTables(),
        getWordPressSiteInfo(),
      ])
      setTables(tbls)
      setSiteInfo(info)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error conectando a la BD. Verifica la configuración.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!sql.trim()) return
    setQueryLoading(true)
    setQueryError(null)
    setQueryRows([])
    setQueryCount(null)
    try {
      const result = await queryWordPressDB(sql)
      setQueryRows(result.rows)
      setQueryCount(result.count)
    } catch (err: unknown) {
      setQueryError((err as { message?: string })?.message ?? 'Error ejecutando query.')
    } finally {
      setQueryLoading(false)
    }
  }

  const queryColumns = queryRows.length > 0 ? Object.keys(queryRows[0]) : []

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex border-b border-gray-200">
        {([
          { key: 'tables', label: 'Tablas' },
          { key: 'query', label: 'Query SQL' },
          { key: 'info', label: 'Info del sitio' },
        ] as const).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === key
                ? 'text-purple-600 border-b-2 border-purple-600'
                : 'text-gray-700 hover:text-gray-900'
            }`}
          >
            {label}
          </button>
        ))}
        <button onClick={load} disabled={loading} className="ml-auto px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700">↻</button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          <p>{error}</p>
          <p className="text-xs text-red-500 mt-1">
            Configura las credenciales MySQL en la pestaña Configuración → Acceso directo a BD.
          </p>
        </div>
      )}

      {/* Tablas */}
      {activeTab === 'tables' && !error && (
        <>
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    {['Tabla', 'Filas (aprox.)', 'Tamaño (MB)', 'Motor', 'Cotejamiento'].map((h) => (
                      <th key={h} className="px-6 py-3 text-left text-sm font-semibold text-gray-900">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {tables.length === 0 ? (
                    <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">Sin tablas.</td></tr>
                  ) : tables.map((t) => (
                    <tr
                      key={t.name}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => {
                        setSql(`SELECT * FROM \`${t.name}\` LIMIT 50`)
                        setActiveTab('query')
                      }}
                    >
                      <td className="px-6 py-4 text-sm font-mono font-medium text-purple-700">{t.name}</td>
                      <td className="px-6 py-4 text-sm text-gray-700">{t.rows?.toLocaleString() ?? '—'}</td>
                      <td className="px-6 py-4 text-sm text-gray-700">{t.size_mb ?? '—'}</td>
                      <td className="px-6 py-4 text-sm text-gray-500">{t.engine}</td>
                      <td className="px-6 py-4 text-xs text-gray-500">{t.collation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-gray-400">Haz clic en una tabla para hacer SELECT automático en la pestaña Query.</p>
        </>
      )}

      {/* Query SQL */}
      {activeTab === 'query' && (
        <div className="space-y-4">
          <form onSubmit={handleQuery} className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Query SQL <span className="text-gray-400 font-normal">(solo SELECT permitido)</span>
              </label>
              <textarea
                rows={5}
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                placeholder="SELECT * FROM `wp_options` WHERE option_name = 'siteurl'"
                spellCheck={false}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={queryLoading || !sql.trim()}
                className="px-6 py-2 text-sm bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg font-medium"
              >
                {queryLoading ? 'Ejecutando...' : 'Ejecutar'}
              </button>
              {queryCount !== null && (
                <span className="text-sm text-gray-500">{queryCount} filas</span>
              )}
            </div>
          </form>

          {queryError && (
            <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700 font-mono">
              {queryError}
            </div>
          )}

          {queryRows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    {queryColumns.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-semibold text-gray-900 font-mono">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {queryRows.map((row, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      {queryColumns.map((col) => (
                        <td key={col} className="px-3 py-2 font-mono text-gray-700 max-w-xs truncate">
                          {row[col] == null ? <span className="text-gray-400 italic">NULL</span> : String(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Info del sitio */}
      {activeTab === 'info' && (
        <>
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
            </div>
          ) : siteInfo ? (
            <div className="rounded-lg border border-gray-200 divide-y divide-gray-200">
              {(
                [
                  { key: 'siteurl', label: 'URL del sitio' },
                  { key: 'blogname', label: 'Nombre' },
                  { key: 'blogdescription', label: 'Descripción' },
                  { key: 'admin_email', label: 'Email admin' },
                  { key: 'db_version', label: 'Versión BD WordPress' },
                ] as const
              ).map(({ key, label }) => (
                <div key={key} className="flex px-4 py-3 gap-4">
                  <span className="text-sm font-medium text-gray-500 w-40 shrink-0">{label}</span>
                  <span className="text-sm text-gray-900 break-all">
                    {siteInfo[key] ?? <span className="text-gray-400 italic">—</span>}
                  </span>
                </div>
              ))}
              <div className="flex px-4 py-3 gap-4">
                <span className="text-sm font-medium text-gray-500 w-40 shrink-0">Total tablas</span>
                <span className="text-sm text-gray-900">{tables.length}</span>
              </div>
            </div>
          ) : !error ? (
            <p className="text-center text-gray-500 py-8">Sin datos de sitio.</p>
          ) : null}
        </>
      )}
    </div>
  )
}
