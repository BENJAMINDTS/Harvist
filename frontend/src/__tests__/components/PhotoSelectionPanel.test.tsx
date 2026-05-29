/**
 * Tests unitarios para PhotoSelectionPanel.
 *
 * PhotoSelectionPanel usa apiClient.get/post directamente.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { apiClient } from '@/api/client'
import PhotoSelectionPanel from '@/components/PhotoSelectionPanel'

describe('PhotoSelectionPanel', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        success: true,
        data: {
          job_id: 'job-1',
          productos: [
            {
              codigo: 'P001',
              nombre: 'Laptop X',
              n_candidates: 2,
              candidates: [
                { index: 0, url: '/img/P001_0.jpg', width: 800, height: 600, size_bytes: 50000 },
                { index: 1, url: '/img/P001_1.jpg', width: 800, height: 600, size_bytes: 55000 },
              ],
              selected_index: null,
            },
          ],
          total_products: 1,
          confirmed: 0,
        },
      },
    })
    vi.mocked(apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { success: true, data: { confirmadas: 1, zip_listo: true } },
    })
  })

  it('renders without crashing', () => {
    render(<PhotoSelectionPanel jobId="job-1" onComplete={vi.fn()} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows product codes after loading', async () => {
    render(<PhotoSelectionPanel jobId="job-1" onComplete={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('P001')).toBeInTheDocument()
    })
  })

  it('shows empty state when no products', async () => {
    vi.mocked(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        success: true,
        data: { job_id: 'job-1', productos: [], total_products: 0, confirmed: 0 },
      },
    })
    render(<PhotoSelectionPanel jobId="job-1" onComplete={vi.fn()} />)
    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).not.toBeInTheDocument()
    })
  })
})
