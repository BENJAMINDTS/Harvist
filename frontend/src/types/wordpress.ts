/**
 * Tipos TypeScript para la integración WordPress / WooCommerce.
 *
 * @author Carlos Vico
 */

export interface WooProduct {
  id: number
  name: string
  slug: string
  sku: string
  status: 'publish' | 'draft' | 'private' | 'pending' | 'trash'
  type: 'simple' | 'variable' | 'grouped' | 'external'
  regular_price: string
  sale_price: string
  price: string
  description: string
  short_description: string
  weight: string
  manage_stock: boolean
  stock_quantity: number | null
  stock_status: 'instock' | 'outofstock' | 'onbackorder'
  categories: WooCategoryRef[]
  images: WooImage[]
  date_created: string
  date_modified: string
}

export interface WooCategoryRef {
  id: number
  name: string
  slug: string
}

export interface WooImage {
  id: number
  src: string
  name: string
  alt: string
}

export interface WooCategory {
  id: number
  name: string
  slug: string
  parent: number
  description: string
  count: number
  children?: WooCategory[]
}

export interface WooOrder {
  id: number
  number: string
  status: WooOrderStatus
  date_created: string
  date_modified: string
  total: string
  currency: string
  customer_id: number
  billing: WooBilling
  shipping: WooShipping
  line_items: WooLineItem[]
  customer_note: string
  payment_method: string
  payment_method_title: string
}

export type WooOrderStatus =
  | 'pending'
  | 'processing'
  | 'on-hold'
  | 'completed'
  | 'cancelled'
  | 'refunded'
  | 'failed'
  | 'trash'

export interface WooBilling {
  first_name: string
  last_name: string
  company: string
  address_1: string
  address_2: string
  city: string
  state: string
  postcode: string
  country: string
  email: string
  phone: string
}

export interface WooShipping {
  first_name: string
  last_name: string
  company: string
  address_1: string
  address_2: string
  city: string
  state: string
  postcode: string
  country: string
}

export interface WooLineItem {
  id: number
  name: string
  product_id: number
  quantity: number
  subtotal: string
  total: string
  sku: string
}

export interface WooCustomer {
  id: number
  email: string
  first_name: string
  last_name: string
  username: string
  role: string
  billing: WooBilling
  shipping: WooShipping
  date_created: string
  orders_count: number
  total_spent: string
}

export interface WooMedia {
  id: number
  date: string
  slug: string
  title: { rendered: string }
  description: { rendered: string }
  source_url: string
  mime_type: string
  media_details: {
    width?: number
    height?: number
    file?: string
    sizes?: Record<string, { source_url: string; width: number; height: number }>
  }
}

export interface WordPressConfigRequest {
  url: string
  consumer_key: string
  consumer_secret: string
}

export interface WordPressConfigResponse {
  url: string
  consumer_key: string
  consumer_secret: string
  configured: boolean
}

export interface WordPressDBConfigRequest {
  host: string
  port: number
  db_name: string
  user: string
  password: string
  prefix: string
}

export interface WordPressDBConfigResponse {
  host: string
  port: number
  db_name: string
  user: string
  password: string
  prefix: string
  configured: boolean
}

export interface DBTable {
  name: string
  rows: number
  size_mb: number
  engine: string
  collation: string
}

export interface WPSiteInfo {
  siteurl: string | null
  blogname: string | null
  blogdescription: string | null
  admin_email: string | null
  db_version: string | null
}
