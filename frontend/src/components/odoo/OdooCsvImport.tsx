/**
 * Modal de importación masiva de productos Odoo desde CSV.
 * Soporta creación y actualización por referencia interna (default_code).
 *
 * @author BenjaminDTS
 */
import { useRef, useState } from 'react'
import { previewOdooCsv, importOdooCsv } from '@/api/client'

interface Props {
  onClose: () => void
  onSuccess: () => void
}

const FIELD_LABELS: Record<string, string> = {
  name: 'Nombre *',
  default_code: 'Referencia interna *',
  active: 'Activo (1/0)',
  priority: 'Favorito (0/1)',
  detailed_type: 'Tipo (consu/service/product)',
  tracking: 'Seguimiento (none/lot/serial)',
  categ_id: 'Categoría (ID numérico)',
  list_price: 'Precio de venta',
  compare_list_price: 'Precio comparativo',
  standard_price: 'Coste',
  weight: 'Peso (kg)',
  volume: 'Volumen (m³)',
  sale_delay: 'Plazo cliente (días)',
  hs_code: 'HS Code',
  sale_ok: 'Se puede vender (1/0)',
  invoice_policy: 'Política facturación (order/delivery)',
  description_sale: 'Descripción ventas',
  purchase_ok: 'Se puede comprar (1/0)',
  purchase_method: 'Control compra (purchase/receive)',
  description_purchase: 'Descripción compras',
  is_published: 'Publicado web (1/0)',
  available_in_pos: 'Disponible POS (1/0)',
  website_meta_title: 'Meta título (SEO)',
  website_meta_description: 'Meta descripción (SEO)',
  website_meta_keywords: 'Meta palabras clave',
  description: 'Descripción interna',
}

type Step = 'upload' | 'map' | 'result'

interface PreviewData {
  headers: string[]
  preview: Record<string, string>[]
  row_count: number
  odoo_fields: string[]
}

interface ImportResult {
  created: number
  updated: number
  skipped: number
  failed: number
  errors: Array<{ row: number; error: string }>
}

export default function OdooCsvImport({ onClose, onSuccess }: Props) {
  const [step, setStep] = useState<Step>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewData, setPreviewData] = useState<PreviewData | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [overwrite, setOverwrite] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    setFile(f)
    setError(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const handlePreview = async () => {
    if (!file) return
    setPreviewing(true)
    setError(null)
    try {
      const data = await previewOdooCsv(file)
      setPreviewData(data)
      const autoMap: Record<string, string> = {}
      data.headers.forEach((h) => {
        if (data.odoo_fields.includes(h)) autoMap[h] = h
        else autoMap[h] = ''
      })
      setMapping(autoMap)
      setStep('map')
    } catch (err) {
      setError((err as Error).message ?? 'Error procesando CSV')
    } finally {
      setPreviewing(false)
    }
  }

  const handleImport = async () => {
    if (!file || !previewData) return
    if (!Object.values(mapping).includes('name')) {
      setError("Debes mapear al menos una columna al campo 'Nombre *'.")
      return
    }
    if (!Object.values(mapping).includes('default_code')) {
      setError("Debes mapear al menos una columna al campo 'Referencia interna *'. Es obligatoria para crear y para detectar duplicados.")
      return
    }
    setImporting(true)
    setError(null)
    try {
      const res = await importOdooCsv(file, mapping, overwrite)
      setResult(res)
      setStep('result')
      if (res.created > 0 || res.updated > 0) onSuccess()
    } catch (err) {
      setError((err as Error).message ?? 'Error importando productos')
    } finally {
      setImporting(false)
    }
  }

  const mappedCount = Object.values(mapping).filter(Boolean).length

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Importar productos desde CSV</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {step === 'upload' && 'Paso 1 de 3 — Seleccionar archivo'}
              {step === 'map' && `Paso 2 de 3 — Mapear columnas (${previewData?.row_count ?? 0} filas)`}
              {step === 'result' && 'Paso 3 de 3 — Resultado'}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4">

          {/* ── Step 1: Upload ── */}
          {step === 'upload' && (
            <div className="space-y-4">
              <div
                className="border-2 border-dashed border-gray-300 rounded-lg p-10 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => inputRef.current?.click()}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,.tsv,.txt"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
                <p className="text-4xl mb-3">📄</p>
                {file ? (
                  <p className="text-sm font-medium text-gray-800">{file.name}</p>
                ) : (
                  <>
                    <p className="text-sm font-medium text-gray-700">Arrastra tu CSV aquí o haz clic para seleccionar</p>
                    <p className="text-xs text-gray-400 mt-1">Soporta cualquier delimitador: coma, punto y coma, tabulador, pipe…</p>
                  </>
                )}
              </div>

              {file && (
                <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
                  <span className="font-medium">{file.name}</span>
                  {' · '}
                  {(file.size / 1024).toFixed(1)} KB
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Mapping ── */}
          {step === 'map' && previewData && (
            <div className="space-y-4">
              {/* Overwrite toggle */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(e) => setOverwrite(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-blue-900">Actualizar productos existentes</p>
                    <p className="text-xs text-blue-700 mt-0.5">
                      Si está activo, los productos con la misma <strong>Referencia interna</strong> se actualizarán con los datos del CSV.
                      Si está inactivo, se omiten y solo se crean los nuevos.
                    </p>
                  </div>
                </label>
              </div>

              {/* Preview table */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Previsualización (primeras {previewData.preview.length} filas)
                </p>
                <div className="overflow-x-auto rounded border border-gray-200">
                  <table className="text-xs w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        {previewData.headers.map((h) => (
                          <th key={h} className="px-3 py-2 text-left font-medium text-gray-700 whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {previewData.preview.map((row, i) => (
                        <tr key={i}>
                          {previewData.headers.map((h) => (
                            <td key={h} className="px-3 py-1.5 text-gray-600 max-w-[140px] truncate">{row[h] ?? ''}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Mapping dropdowns */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Mapeo de columnas — {mappedCount} mapeadas de {previewData.headers.length}
                </p>
                <div className="space-y-2">
                  {previewData.headers.map((csvCol) => (
                    <div key={csvCol} className="flex items-center gap-3">
                      <span className="w-40 text-sm font-medium text-gray-700 truncate shrink-0" title={csvCol}>
                        {csvCol}
                      </span>
                      <span className="text-gray-400 shrink-0">→</span>
                      <select
                        value={mapping[csvCol] ?? ''}
                        onChange={(e) => setMapping((prev) => ({ ...prev, [csvCol]: e.target.value }))}
                        className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      >
                        <option value="">— Ignorar —</option>
                        {previewData.odoo_fields.map((f) => (
                          <option key={f} value={f}>{FIELD_LABELS[f] ?? f}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Step 3: Result ── */}
          {step === 'result' && result && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
                  <p className="text-3xl font-bold text-green-700">{result.created}</p>
                  <p className="text-xs text-green-600 mt-1">Creados</p>
                </div>
                <div className={`border rounded-lg p-4 text-center ${result.updated > 0 ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'}`}>
                  <p className={`text-3xl font-bold ${result.updated > 0 ? 'text-blue-700' : 'text-gray-400'}`}>{result.updated}</p>
                  <p className={`text-xs mt-1 ${result.updated > 0 ? 'text-blue-600' : 'text-gray-400'}`}>Actualizados</p>
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
                  <p className="text-3xl font-bold text-gray-400">{result.skipped}</p>
                  <p className="text-xs text-gray-400 mt-1">Omitidos</p>
                </div>
                <div className={`border rounded-lg p-4 text-center ${result.failed > 0 ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'}`}>
                  <p className={`text-3xl font-bold ${result.failed > 0 ? 'text-red-700' : 'text-gray-400'}`}>{result.failed}</p>
                  <p className={`text-xs mt-1 ${result.failed > 0 ? 'text-red-600' : 'text-gray-400'}`}>Fallidos</p>
                </div>
              </div>

              {result.errors.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Errores</p>
                  <div className="max-h-40 overflow-y-auto space-y-1">
                    {result.errors.map((e) => (
                      <div key={e.row} className="text-xs bg-red-50 border border-red-100 rounded px-3 py-2 text-red-700">
                        <span className="font-medium">Fila {e.row}:</span> {e.error}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="mt-4 bg-red-50 border-l-4 border-red-400 p-3 rounded text-sm text-red-700">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex gap-3 flex-shrink-0">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
          >
            {step === 'result' ? 'Cerrar' : 'Cancelar'}
          </button>

          {step === 'upload' && (
            <button
              onClick={handlePreview}
              disabled={!file || previewing}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {previewing ? 'Procesando...' : 'Siguiente →'}
            </button>
          )}

          {step === 'map' && (
            <>
              <button
                onClick={() => setStep('upload')}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
              >
                ← Volver
              </button>
              <button
                onClick={handleImport}
                disabled={importing || mappedCount === 0}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
              >
                {importing
                  ? 'Importando...'
                  : overwrite
                    ? `Importar / actualizar ${previewData?.row_count ?? ''} productos`
                    : `Importar ${previewData?.row_count ?? ''} productos`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
