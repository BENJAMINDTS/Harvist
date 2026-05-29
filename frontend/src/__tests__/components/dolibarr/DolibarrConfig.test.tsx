/**
 * Tests unitarios para DolibarrConfig.
 * @author BenjaminDTS
 */
import { render, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
  getDolibarrDBConfig: vi.fn(),
  saveDolibarrDBConfig: vi.fn(),
}))

import { getDolibarrDBConfig } from '@/api/client'
import DolibarrConfig from '@/components/dolibarr/DolibarrConfig'

describe('DolibarrConfig', () => {
  beforeEach(() => {
    vi.mocked(getDolibarrDBConfig).mockResolvedValue({
      dolibarr_url: 'https://dolibarr.test',
      dolibarr_api_key: 'key-xxx',
    } as never)
  })

  it('renders without crashing', () => {
    render(<DolibarrConfig onSaved={vi.fn()} />)
    expect(document.body).toBeInTheDocument()
  })

  it('shows form fields', async () => {
    render(<DolibarrConfig onSaved={vi.fn()} />)
    await waitFor(() => {
      const inputs = document.querySelectorAll('input')
      expect(inputs.length).toBeGreaterThan(0)
    })
  })
})
