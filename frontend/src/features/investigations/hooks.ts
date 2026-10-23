import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'

const keys = {
  all: ['investigations'] as const,
  list: (limit: number, offset: number) => [...keys.all, 'list', limit, offset] as const,
  stats: () => [...keys.all, 'stats'] as const,
  detail: (id: string) => [...keys.all, 'detail', id] as const,
}

export function useInvestigationList(limit = 10, offset = 0) {
  return useQuery({
    queryKey: keys.list(limit, offset),
    queryFn: () => api.listInvestigations(limit, offset),
    placeholderData: keepPreviousData,
  })
}

export function useInvestigationStats() {
  return useQuery({ queryKey: keys.stats(), queryFn: () => api.getInvestigationStats() })
}

export function useInvestigation(id: string) {
  return useQuery({ queryKey: keys.detail(id), queryFn: () => api.getInvestigation(id) })
}

export function useCreateInvestigation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (question: string) => api.createInvestigation(question),
    onSuccess: (created) => {
      queryClient.setQueryData(keys.detail(created.id), created)
      return queryClient.invalidateQueries({ queryKey: keys.all })
    },
  })
}
