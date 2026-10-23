import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { PaperSearchParams } from '../../api/types'

export function usePaperSearch(params: PaperSearchParams | null) {
  return useQuery({
    queryKey: ['papers', 'search', params],
    queryFn: () => api.searchPapers(params!),
    enabled: params !== null,
    placeholderData: keepPreviousData,
    // Results are cached server-side for 24h; avoid re-spending quota on refocus.
    staleTime: 5 * 60_000,
  })
}

export function usePaper(id: string) {
  return useQuery({ queryKey: ['papers', 'detail', id], queryFn: () => api.getPaper(id) })
}
