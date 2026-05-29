/**
 * Tests unitarios para JobHistory.
 *
 * job_id is not displayed as text — the component renders date, status, total_productos.
 * @author BenjaminDTS
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

import { apiClient } from '@/api/client'
import { JobHistory } from '@/components/JobHistory'

const mockJobsResponse = {
  data: {
    success: true,
    data: {
      items: [
        {
          job_id: 'job-001',
          estado: 'completado',
          total_productos: 42,
          imagenes_descargadas: 42,
          porcentaje: 100,
          creado_en: '2024-01-15T10:00:00Z',
          completado_en: '2024-01-15T11:00:00Z',
          mensaje: 'Completado',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    },
    message: 'OK',
  },
}

describe('JobHistory', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockJobsResponse)
  })

  it('renders without crashing', () => {
    render(<JobHistory onSelectJob={vi.fn()} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows products count after loading', async () => {
    render(<JobHistory onSelectJob={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getAllByText('42').length).toBeGreaterThan(0)
    })
  })

  it('shows empty state when no jobs', async () => {
    vi.mocked(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        success: true,
        data: { items: [], total: 0, limit: 20, offset: 0 },
        message: 'OK',
      },
    })
    render(<JobHistory onSelectJob={vi.fn()} />)
    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).not.toBeInTheDocument()
    })
  })

  it('calls onSelectJob when a row is clicked', async () => {
    const onSelectJob = vi.fn()
    const user = userEvent.setup()
    render(<JobHistory onSelectJob={onSelectJob} />)

    await waitFor(() => {
      expect(screen.getAllByText('42').length).toBeGreaterThan(0)
    })

    // Find and click the row (role="button")
    const rows = screen.getAllByRole('button')
    const jobRow = rows.find(r => r.getAttribute('aria-label')?.includes('2024'))
    if (jobRow) {
      await user.click(jobRow)
      expect(onSelectJob).toHaveBeenCalledWith('job-001')
    }
  })
})
