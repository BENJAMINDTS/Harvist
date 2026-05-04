/**
 * Módulo de gestión de stock de Dolibarr.
 *
 * @author BenjaminDTS
 */
import { useEffect, useState } from 'react'
import {
  listDolibarrWarehouses,
  listDolibarrProducts,
  getDolibarrProductStock,
} from '@/api/client'
import { type DolibarrWarehouse } from '@/types/dolibarr'

interface StockRow {
  id: number
  ref: string
  label: string
  stock_total: number
  warehouses: Array<{ warehouse_id: number; warehouse_label: string; qty: number }>
}

export default function DolibarrStocks() {
  const [warehouses, setWarehouses] = useState<DolibarrWarehouse[]>([])
  const [stocks, setStocks] = useState<StockRow[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<number | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        setLoading(true)

        // Cargar almacenes
        const warehousesData = await listDolibarrWarehouses()
        setWarehouses(warehousesData.items)
        if (warehousesData.items.length > 0) {
          setSelectedWarehouseId(warehousesData.items[0].id)
        }

        // Cargar productos y stock
        const productsData = await listDolibarrProducts(50)
        const stockRows: StockRow[] = []

        for (const product of productsData.items) {
          try {
            const stockInfo = await getDolibarrProductStock(product.id)
            stockRows.push({
              id: product.id,
              ref: product.ref,
              label: product.label,
              stock_total: stockInfo.stock_total,
              warehouses: stockInfo.warehouses,
            })
          } catch (err) {
            // Ignorar errores en stock individual
            console.error(`Error loading stock for product ${product.id}:`, err)
          }
        }

        setStocks(stockRows)
      } catch (err) {
        console.error('Error loading warehouses/stocks:', err)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const getWarehouseQty = (
    warehouses: StockRow['warehouses'],
    warehouseId: number,
  ): number => {
    return warehouses.find((w) => w.warehouse_id === warehouseId)?.qty ?? 0
  }

  return (
    <div className="space-y-6">
      {/* Selector de almacén */}
      {warehouses.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Filtrar por almacén
          </label>
          <select
            value={selectedWarehouseId ?? ''}
            onChange={(e) => setSelectedWarehouseId(parseInt(e.target.value))}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="">-- Todos --</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Tabla de stock */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Referencia
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Nombre
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Stock Total
              </th>
              {selectedWarehouseId && (
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                  {warehouses.find((w) => w.id === selectedWarehouseId)?.label ||
                    'Almacén'}
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td
                  colSpan={selectedWarehouseId ? 4 : 3}
                  className="px-6 py-8 text-center text-gray-500"
                >
                  Cargando stock...
                </td>
              </tr>
            ) : stocks.length === 0 ? (
              <tr>
                <td
                  colSpan={selectedWarehouseId ? 4 : 3}
                  className="px-6 py-8 text-center text-gray-500"
                >
                  Sin productos
                </td>
              </tr>
            ) : (
              stocks.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    {s.ref}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">{s.label}</td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        s.stock_total > 0
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {s.stock_total}
                    </span>
                  </td>
                  {selectedWarehouseId && (
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {getWarehouseQty(s.warehouses, selectedWarehouseId)}
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Desglose por almacén (sin filtro) */}
      {!selectedWarehouseId && stocks.length > 0 && (
        <div className="grid grid-cols-1 gap-4">
          <h3 className="font-semibold text-gray-900">Desglose por almacén</h3>
          {warehouses.map((w) => {
            const totalInWarehouse = stocks.reduce(
              (sum, s) => sum + getWarehouseQty(s.warehouses, w.id),
              0,
            )
            return (
              <div
                key={w.id}
                className="bg-gray-50 p-4 rounded-lg border border-gray-200"
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium text-gray-900">{w.label}</span>
                  <span className="text-lg font-semibold text-blue-600">
                    {totalInWarehouse} productos
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
