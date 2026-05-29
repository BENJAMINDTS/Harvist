/**
 * Tests unitarios para ReviewPanel.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

import { apiClient } from '@/api/client'
import ReviewPanel from '@/components/ReviewPanel'

describe('ReviewPanel', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        success: true,
        data: {
          items: [
            {
              codigo: 'P001',
              nombre: 'Laptop Gaming',
              descripcion_corta: 'Potente laptop',
              descripcion_larga: 'Descripción completa...',
              status: 'pending',
              edited_text: null,
              edited_larga: null,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        },
      },
    })
    vi.mocked(apiClient.patch as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { success: true, data: {} },
    })
  })

  it('renders without crashing', () => {
    render(<ReviewPanel jobId="job-1" onComplete={vi.fn()} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows review items after loading', async () => {
    render(<ReviewPanel jobId="job-1" onComplete={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('Laptop Gaming')).toBeInTheDocument()
    })
  })
})
