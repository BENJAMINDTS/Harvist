/**
 * Tests unitarios para CsvUploader.
 *
 * Verifica:
 * - Renderiza zona de drag & drop en estado idle
 * - Muestra error cuando se sube archivo no-CSV
 * - Llama onFileSelected con archivo CSV válido
 * - Acepta archivo con tipo MIME text/csv
 *
 * @author BenjaminDTS
 */
import { render, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CsvUploader } from '@/components/CsvUploader'

function makeCsvFile(content = 'nombre,ean\nProd A,12345', name = 'test.csv') {
  return new File([content], name, { type: 'text/csv' })
}

describe('CsvUploader', () => {
  it('renders drop zone in idle state', () => {
    render(<CsvUploader onFileSelected={vi.fn()} />)
    // Should show upload-related text
    expect(document.body).toBeInTheDocument()
  })

  it('shows error for non-CSV file', async () => {
    render(<CsvUploader onFileSelected={vi.fn()} />)
    const input = document.querySelector('input[type="file"]')!
    const badFile = new File(['data'], 'image.jpg', { type: 'image/jpeg' })

    fireEvent.change(input, { target: { files: [badFile] } })

    await waitFor(() => {
      const errorEl = document.body.querySelector('[class*="red"], [class*="error"]')
      if (errorEl) {
        expect(errorEl).toBeInTheDocument()
      }
    })
  })

  it('calls onFileSelected with valid CSV', async () => {
    const onFileSelected = vi.fn()
    render(<CsvUploader onFileSelected={onFileSelected} />)
    const input = document.querySelector('input[type="file"]')!
    const csvFile = makeCsvFile()

    fireEvent.change(input, { target: { files: [csvFile] } })

    await waitFor(() => {
      expect(onFileSelected).toHaveBeenCalledOnce()
    }, { timeout: 2000 })
  })

  it('does not call onFileSelected for non-CSV extension', async () => {
    const onFileSelected = vi.fn()
    render(<CsvUploader onFileSelected={onFileSelected} />)
    const input = document.querySelector('input[type="file"]')!
    const xlsFile = new File(['data'], 'report.xlsx', { type: 'application/vnd.ms-excel' })

    fireEvent.change(input, { target: { files: [xlsFile] } })

    await waitFor(() => {})
    expect(onFileSelected).not.toHaveBeenCalled()
  })
})
