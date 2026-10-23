import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'

const keys = {
  all: ['investigations'] as const,
  list: (limit: number) => [...keys.all, 'list', limit] as const,
  detail: (id: string) => [...keys.all, 'detail', id] as const,
}

export function useRecentInvestigations(limit = 10) {
  return useQuery({ queryKey: keys.list(limit), queryFn: () => api.listInvestigations(limit) })
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
