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
  barcode?: string
  barcode_type?: string
  tobatch?: number
  accountancy_code_sell?: string
  accountancy_code_sell_export?: string
  accountancy_code_buy?: string
  accountancy_code_buy_intra?: string
  url?: string
  fk_default_warehouse?: number
  finished?: number
  weight?: number
  weight_units?: number
  length?: number
  width?: number
  height?: number
  length_units?: number
  surface?: number
  surface_units?: number
  volume?: number
  volume_units?: number
  customcode?: string
  country_id?: number
  /** Extra/custom fields configured in this Dolibarr instance. Keys are "options_fieldname". */
  array_options?: Record<string, unknown>
}

export type DolibarrFieldType = 'text' | 'number' | 'select' | 'boolean' | 'textarea' | 'date'

export interface DolibarrFieldOption {
  value: string
  label: string
}

export interface DolibarrFieldSchema {
  key: string
  label: string
  type: DolibarrFieldType
  required: boolean
  section: string
  is_extra: boolean
  options?: DolibarrFieldOption[] | null
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

export interface DolibarrStats {
  configured: boolean
  thirdparties: {
    total: number
    customers: number
    suppliers: number
    has_more: boolean
  } | null
  invoices: {
    customer: number
    supplier: number
    has_more_customer: boolean
    has_more_supplier: boolean
  } | null
}

export interface DolibarrDBConfig {
  host: string
  port: number
  db_name: string
  user: string
  password: string
  prefix: string
  configured: boolean
}

export interface DolibarrDBConfigCreate {
  host: string
  port: number
  db_name: string
  user: string
  password: string
  prefix: string
}

export interface DolibarrExtraField {
  attrname: string
  label: string
  type: string
  type_normalized: DolibarrFieldType
  elementtype: string
  size: string
  required: boolean
  fielddefault: string
}

export interface DolibarrExtraFieldCreate {
  attrname: string
  label: string
  type: string
  elementtype: string
  size: string
  required: boolean
  fielddefault: string
}

export interface CsvImportPreview {
  headers: string[]
  preview: Record<string, string>[]
  total_rows: number
}

export interface CsvImportRowResult {
  row: number
  ref: string
  action: 'created' | 'updated' | 'skipped' | 'error'
  dolibarr_id: number | null
  error: string | null
}

export interface CsvImportResponse {
  total: number
  created: number
  updated: number
  skipped: number
  errors: number
  results: CsvImportRowResult[]
}
