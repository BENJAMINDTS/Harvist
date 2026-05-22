/**
 * Tests unitarios del cliente HTTP y funciones de API de Harvist.
 *
 * Cubre:
 * - buildWsUrl: construcción correcta de URLs WebSocket (ws:// y wss://)
 * - Interceptor de error: normalización de errores Axios a ApiError
 * - getBrands: extracción del array de marcas desde la respuesta envuelta
 * - buildWsUrl con HTTPS: produce wss://
 * - validateBrands: serialización correcta del body
 * - confirmPhotoSelection: serialización correcta del body
 * - reviewDescription: método PATCH con body correcto
 * - getBrandsPending: extracción de items desde la respuesta
 *
 * @author BenjaminDTS | Carlos Vico
 * @version 1.0.0
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import {
  apiClient,
  buildWsUrl,
  getBrands,
  validateBrands,
  confirmPhotoSelection,
  reviewDescription,
  getBrandsPending,
  downloadBrandsCsv,
  type BrandEntry,
  type BrandValidationRequest,
  type ApiError,
} from '@/api/client'


describe('buildWsUrl', () => {
  /**
   * Verifica la construcción de URLs WebSocket en entorno HTTP.
   *
   * @author BenjaminDTS
   */

  it('genera ws:// cuando el protocolo es http:', () => {
    Object.defineProperty(window, 'location', {
      value: { protocol: 'http:', host: 'localhost:5173' },
      configurable: true,
    })
    const url = buildWsUrl('abc-123')
    expect(url).toBe('ws://localhost:5173/api/v1/jobs/abc-123/ws')
  })

  it('genera wss:// cuando el protocolo es https:', () => {
    Object.defineProperty(window, 'location', {
      value: { protocol: 'https:', host: 'app.harvist.com' },
      configurable: true,
    })
    const url = buildWsUrl('xyz-456')
    expect(url).toBe('wss://app.harvist.com/api/v1/jobs/xyz-456/ws')
  })

  it('incluye el jobId en la ruta', () => {
    Object.defineProperty(window, 'location', {
      value: { protocol: 'http:', host: 'localhost:8000' },
      configurable: true,
    })
    const jobId = 'job-uuid-9999'
    expect(buildWsUrl(jobId)).toContain(jobId)
  })
})

describe('Interceptor de error Axios', () => {
  /**
   * Verifica que el interceptor de respuesta normaliza errores HTTP a ApiError.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => {
    mock = new MockAdapter(apiClient)
  })

  afterEach(() => {
    mock.restore()
  })

  it('normaliza un 404 con detail a ApiError', async () => {
    mock.onGet('/test-404').reply(404, { detail: 'No encontrado.' })

    await expect(apiClient.get('/test-404')).rejects.toMatchObject({
      status: 404,
      message: 'No encontrado.',
    })
  })

  it('normaliza un 500 sin detail usando message del cuerpo', async () => {
    mock.onGet('/test-500').reply(500, { message: 'Error interno.' })

    await expect(apiClient.get('/test-500')).rejects.toMatchObject({
      status: 500,
      message: 'Error interno.',
    })
  })

  it('usa el mensaje de Axios como fallback cuando el body está vacío', async () => {
    mock.onGet('/test-empty').reply(502, {})

    let err!: ApiError
    await apiClient.get('/test-empty').catch((e: unknown) => { err = e as ApiError })
    expect(err.status).toBe(502)
    // Cuando body no tiene detail ni message, el interceptor cae en error.message
    // que Axios rellena con "Request failed with status code 502"
    expect(typeof err.message).toBe('string')
    expect(err.message.length).toBeGreaterThan(0)
  })

  it('status 0 cuando no hay respuesta (timeout / red)', async () => {
    mock.onGet('/test-timeout').networkError()

    await expect(apiClient.get('/test-timeout')).rejects.toMatchObject({
      status: 0,
    })
  })
})

describe('getBrands', () => {
  /**
   * Verifica que getBrands desenvuelve la respuesta estándar y devuelve el array.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => { mock = new MockAdapter(apiClient) })
  afterEach(() => { mock.restore() })

  it('devuelve el array de marcas de la respuesta envuelta', async () => {
    const brands: BrandEntry[] = [
      { codigo: 'P001', ean: '8411', brand_name: 'Nike', manufacturer: null, source: 'amazon', confidence: 'high' },
      { codigo: 'P002', ean: '8412', brand_name: null, manufacturer: null, source: 'not_found', confidence: 'low' },
    ]
    mock.onGet('/jobs/job-1/brands').reply(200, {
      success: true,
      data: { brands, brands_resolved: 1, brands_not_found: 1 },
      message: 'OK',
    })

    const result = await getBrands('job-1')
    expect(result).toHaveLength(2)
    expect(result[0].brand_name).toBe('Nike')
    expect(result[1].source).toBe('not_found')
  })
})

describe('getBrandsPending', () => {
  /**
   * Verifica que getBrandsPending extrae items de la respuesta envuelta.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => { mock = new MockAdapter(apiClient) })
  afterEach(() => { mock.restore() })

  it('devuelve la lista de marcas pendientes', async () => {
    mock.onGet('/jobs/job-1/brands/pending').reply(200, {
      success: true,
      data: {
        items: [
          { ean: '8411000', brand_name: 'Adidas', source: 'amazon', confidence: 'high', prefijo: '8411000' },
        ],
      },
      message: 'OK',
    })

    const result = await getBrandsPending('job-1')
    expect(result).toHaveLength(1)
    expect(result[0].brand_name).toBe('Adidas')
  })
})

describe('validateBrands', () => {
  /**
   * Verifica que validateBrands serializa correctamente el body y devuelve el resumen.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => { mock = new MockAdapter(apiClient) })
  afterEach(() => { mock.restore() })

  it('envía el body correcto y devuelve el resumen', async () => {
    const request: BrandValidationRequest = {
      items: [
        { ean: '8411000', brand_name: 'Nike', action: 'accept' },
        { ean: '8412000', brand_name: 'Puma', action: 'reject' },
      ],
    }
    mock.onPost('/jobs/job-1/brands/validate').reply((config) => {
      const body = JSON.parse(config.data as string) as BrandValidationRequest
      expect(body.items).toHaveLength(2)
      expect(body.items[0].action).toBe('accept')
      return [200, { success: true, data: { accepted: 1, rejected: 1, edited: 0 }, message: 'OK' }]
    })

    const result = await validateBrands('job-1', request)
    expect(result.accepted).toBe(1)
    expect(result.rejected).toBe(1)
    expect(result.edited).toBe(0)
  })
})

describe('confirmPhotoSelection', () => {
  /**
   * Verifica que confirmPhotoSelection serializa las selecciones y devuelve el resumen.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => { mock = new MockAdapter(apiClient) })
  afterEach(() => { mock.restore() })

  it('envía selections y devuelve confirmadas + zip_listo', async () => {
    mock.onPost('/jobs/job-1/photos/confirm').reply((config) => {
      const body = JSON.parse(config.data as string) as { selections: { codigo: string; selected_index: number }[] }
      expect(body.selections).toHaveLength(1)
      expect(body.selections[0].selected_index).toBe(2)
      return [200, { success: true, data: { confirmadas: 1, zip_listo: true }, message: 'OK' }]
    })

    const result = await confirmPhotoSelection('job-1', [{ codigo: 'P001', selected_index: 2 }])
    expect(result.confirmadas).toBe(1)
    expect(result.zip_listo).toBe(true)
  })
})

describe('reviewDescription', () => {
  /**
   * Verifica que reviewDescription usa PATCH y serializa el body correctamente.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => { mock = new MockAdapter(apiClient) })
  afterEach(() => { mock.restore() })

  it('aprueba una descripción con action=approve', async () => {
    mock.onPatch('/jobs/job-1/descriptions/P001').reply(200, {
      success: true,
      data: { codigo: 'P001', status: 'approved', edited_text: null },
      message: 'OK',
    })

    const result = await reviewDescription('job-1', 'P001', { action: 'approve' })
    expect(result.status).toBe('approved')
    expect(result.codigo).toBe('P001')
  })

  it('edita una descripción con action=edit y edited_text', async () => {
    mock.onPatch('/jobs/job-1/descriptions/P002').reply(200, {
      success: true,
      data: { codigo: 'P002', status: 'approved', edited_text: 'Nuevo texto.' },
      message: 'OK',
    })

    const result = await reviewDescription('job-1', 'P002', { action: 'edit', edited_text: 'Nuevo texto.' })
    expect(result.edited_text).toBe('Nuevo texto.')
  })
})

describe('downloadBrandsCsv', () => {
  /**
   * Verifica que downloadBrandsCsv devuelve un Blob con el CSV.
   *
   * @author BenjaminDTS
   */
  let mock: MockAdapter

  beforeEach(() => { mock = new MockAdapter(apiClient) })
  afterEach(() => { mock.restore() })

  it('hace GET a la ruta correcta con responseType blob y devuelve datos', async () => {
    // axios-mock-adapter en jsdom no produce Blob nativo; verificamos
    // que la petición se realiza a la ruta esperada y devuelve algo truthy.
    const csvContent = 'codigo,ean,brand_name\nP001,8411,Nike\n'
    mock.onGet('/files/job-1/brands').reply(200, csvContent, { 'content-type': 'text/csv' })

    const result = await downloadBrandsCsv('job-1')
    expect(result).toBeTruthy()
  })
})
