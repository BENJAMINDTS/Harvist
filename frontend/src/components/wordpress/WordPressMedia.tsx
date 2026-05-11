/**
 * Panel del Media Library de WordPress.
 * Lista archivos y permite subir nuevas imágenes.
 *
 * @author Carlos Vico
 */
import { useEffect, useRef, useState } from 'react'
import { listWordPressMedia, uploadWordPressMedia } from '@/api/client'
import type { WooMedia } from '@/types/wordpress'

export default function WordPressMedia() {
  const [media, setMedia] = useState<WooMedia[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [preview, setPreview] = useState<WooMedia | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const limit = 50

  const load = async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const items = await listWordPressMedia(limit, newOffset)
      setMedia(items)
      setOffset(newOffset)
      setHasMore(items.length === limit)
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Error cargando media.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const created = await uploadWordPressMedia(file)
      setMedia((prev) => [created, ...prev])
    } catch (err: unknown) {
      setUploadError((err as { message?: string })?.message ?? 'Error subiendo archivo.')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const thumbnailUrl = (m: WooMedia): string => {
    const thumb = m.media_details?.sizes?.thumbnail?.source_url
    return thumb ?? m.source_url
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg font-medium"
        >
          {uploading ? 'Subiendo...' : '+ Subir imagen'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={handleUpload}
        />
        <button onClick={() => load(offset)} disabled={loading} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">↻ Refrescar</button>
        {uploadError && (
          <span className="text-sm text-red-600">{uploadError}</span>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
        </div>
      ) : media.length === 0 ? (
        <p className="text-center text-gray-500 py-8">Sin archivos en el Media Library.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {media.map((m) => (
            <button
              key={m.id}
              onClick={() => setPreview(m)}
              className="group relative aspect-square rounded-lg overflow-hidden border border-gray-200 hover:ring-2 hover:ring-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <img
                src={thumbnailUrl(m)}
                alt={m.title?.rendered ?? m.slug}
                className="w-full h-full object-cover group-hover:opacity-90 transition-opacity"
                loading="lazy"
              />
              <div className="absolute inset-x-0 bottom-0 bg-black/50 px-1 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <p className="text-white text-xs truncate">{m.title?.rendered ?? m.slug}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center justify-end gap-2">
        <button onClick={() => load(Math.max(0, offset - limit))} disabled={offset === 0 || loading} className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 text-sm">Anterior</button>
        <button onClick={() => load(offset + limit)} disabled={!hasMore || loading} className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 text-sm">Siguiente</button>
      </div>

      {/* Preview modal */}
      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-70"
          onClick={() => setPreview(null)}
        >
          <div
            className="bg-white rounded-lg shadow-lg max-w-2xl w-full mx-4 p-4 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <h3 className="text-base font-semibold text-gray-900 truncate max-w-xs">
                {preview.title?.rendered ?? preview.slug}
              </h3>
              <button onClick={() => setPreview(null)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>
            <img
              src={preview.source_url}
              alt={preview.title?.rendered ?? ''}
              className="w-full max-h-96 object-contain rounded"
            />
            <div className="text-xs text-gray-500 space-y-1">
              <p><span className="font-medium">ID:</span> {preview.id}</p>
              <p><span className="font-medium">MIME:</span> {preview.mime_type}</p>
              {preview.media_details?.width && (
                <p><span className="font-medium">Dimensiones:</span> {preview.media_details.width} × {preview.media_details.height}px</p>
              )}
              <p className="truncate"><span className="font-medium">URL:</span> {preview.source_url}</p>
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(preview.source_url)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
            >
              Copiar URL
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
