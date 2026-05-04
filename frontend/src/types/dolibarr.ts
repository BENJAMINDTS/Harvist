/**
 * Tipos TypeScript para la integración Dolibarr.
 *
 * @author BenjaminDTS
 */

export interface IntegrationStatus {
  platform: string
  configured: boolean
  healthy: boolean | null
  message: string
}

export interface PaginatedResponse<T = Record<string, unknown>> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface DolibarrProduct {
  id: number
  ref: string
  label: string
  description: string
  price: number
  status: number
  type: number
}

export interface DolibarrThirdparty {
  id: number
  name: string
  client: number
  supplier: number
  email: string
  phone: string
  address: string
  town: string
  zip: string
}

export interface DolibarrOrder {
  id: number
  ref: string
  socid: number
  date: number
  statut: number
  total_ttc: number
}

export interface DolibarrInvoice {
  id: number
  ref: string
  socid: number
  date: number
  statut: number
  total_ttc: number
  remaintopay: number
}

export interface DolibarrWarehouse {
  id: number
  ref: string
  label: string
  description: string
}

export interface SyncFromJobRequest {
  job_id: string
  product_codes: string[]
  overwrite: boolean
}

export type ThirdpartyMode = 'all' | 'customers' | 'suppliers'
export type OrderType = 'customer' | 'supplier'
export type InvoiceType = 'customer' | 'supplier'
