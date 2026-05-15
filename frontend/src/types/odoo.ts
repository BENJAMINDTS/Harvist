/**
 * Tipos TypeScript para la integración Odoo.
 *
 * @author Carlitos6712
 */

export interface OdooProduct {
  id: number
  name: string
  default_code: string | false
  description: string | false
  description_sale: string | false
  description_purchase: string | false
  list_price: number
  compare_list_price: number
  standard_price: number
  detailed_type: 'consu' | 'service' | 'product'
  type: 'consu' | 'service' | 'product'
  categ_id: [number, string] | false
  uom_id: [number, string] | false
  uom_po_id: [number, string] | false
  active: boolean
  sale_ok: boolean
  purchase_ok: boolean
  qty_available: number
  volume: number
  weight: number
  tracking: 'none' | 'lot' | 'serial'
  priority: string
  hs_code: string | false
  sale_delay: number
  invoice_policy: string | false
  purchase_method: string | false
  is_published: boolean
  available_in_pos: boolean
  website_meta_title: string | false
  website_meta_description: string | false
  website_meta_keywords: string | false
  public_categ_ids: number[]
}

export interface OdooCategory {
  id: number
  name: string
  complete_name: string
  parent_id: [number, string] | false
  child_id: number[]
}

export interface OooCategoryTree extends OdooCategory {
  children: OooCategoryTree[]
}

export interface OdooPartner {
  id: number
  name: string
  email: string | false
  phone: string | false
  mobile: string | false
  street: string | false
  city: string | false
  zip: string | false
  country_id: [number, string] | false
  vat: string | false
  customer_rank: number
  supplier_rank: number
  active: boolean
  is_company: boolean
  comment: string | false
}

export interface OooPurchase {
  id: number
  name: string
  partner_id: [number, string] | false
  date_order: string | false
  date_approve: string | false
  state: 'draft' | 'sent' | 'purchase' | 'done' | 'cancel'
  amount_total: number
  currency_id: [number, string] | false
  order_line: number[]
  notes: string | false
  user_id: [number, string] | false
}

export interface OdooSale {
  id: number
  name: string
  partner_id: [number, string] | false
  date_order: string | false
  validity_date: string | false
  state: 'draft' | 'sent' | 'sale' | 'done' | 'cancel'
  amount_total: number
  currency_id: [number, string] | false
  order_line: number[]
  note: string | false
  user_id: [number, string] | false
  invoice_status: 'upselling' | 'invoiced' | 'to invoice' | 'no'
}

export interface OdooInvoice {
  id: number
  name: string
  partner_id: [number, string] | false
  invoice_date: string | false
  invoice_date_due: string | false
  move_type: 'out_invoice' | 'in_invoice' | 'out_refund' | 'in_refund'
  state: 'draft' | 'posted' | 'cancel'
  amount_untaxed: number
  amount_tax: number
  amount_total: number
  amount_residual: number
  currency_id: [number, string] | false
  invoice_line_ids: number[]
  payment_state: 'not_paid' | 'in_payment' | 'paid' | 'partial' | 'reversed' | 'invoicing_legacy'
}

export interface OdooStockLine {
  id: number
  product_id: [number, string] | false
  location_id: [number, string] | false
  quantity: number
  reserved_quantity: number
  inventory_quantity: number
  inventory_diff_quantity: number
  inventory_date: string | false
  lot_id: [number, string] | false
  package_id: [number, string] | false
  owner_id: [number, string] | false
  user_id: [number, string] | false
  in_date: string | false
}

export interface OdooLocation {
  id: number
  name: string
  complete_name: string
  usage: string
  active: boolean
}

export interface OdooConfigRequest {
  url: string
  db: string
  user: string
  password: string
}

export interface OdooConfigResponse {
  url: string
  db: string
  user: string
  password: string
  configured: boolean
}

export type PartnerMode = 'customer' | 'supplier' | 'all'
export type OdooInvoiceType = 'customer' | 'supplier'

export type OdooPropertyType = 'char' | 'integer' | 'float' | 'boolean' | 'date' | 'many2one' | 'tags'

export interface OdooPropertyDefinition {
  name: string
  type: OdooPropertyType
  string: string
  default: string | number | boolean
  view_in_cards: boolean
}

export interface OdooPropertyValue {
  name: string
  type: OdooPropertyType
  string: string
  value: string | number | boolean | null
}
