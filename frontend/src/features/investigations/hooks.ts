import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'

const keys = {
  all: ['investigations'] as const,
  list: (limit: number, offset: number) => [...keys.all, 'list', limit, offset] as const,
  stats: () => [...keys.all, 'stats'] as const,
  detail: (id: string) => [...keys.all, 'detail', id] as const,
  tasks: (id: string) => [...keys.all, 'tasks', id] as const,
  papers: (id: string) => [...keys.all, 'papers', id] as const,
  evidence: (id: string) => [...keys.all, 'evidence', id] as const,
}

const POLL_MS = 2000
const ACTIVE_TASK = new Set(['pending', 'running'])

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

/** Polls while any task is pending or running; stops once work settles. */
export function useInvestigationTasks(id: string) {
  return useQuery({
    queryKey: keys.tasks(id),
    queryFn: () => api.getInvestigationTasks(id),
    refetchInterval: (query) =>
      query.state.data?.some((task) => ACTIVE_TASK.has(task.status)) ? POLL_MS : false,
  })
}

export function useDiscoveredPapers(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.papers(id),
    queryFn: () => api.getDiscoveredPapers(id),
    enabled,
  })
}

export function useEvidence(id: string, enabled: boolean) {
  return useQuery({ queryKey: keys.evidence(id), queryFn: () => api.getEvidence(id), enabled })
}

export function usePipelineStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['system', 'pipeline'],
    queryFn: () => api.getPipelineStatus(),
    enabled,
    refetchInterval: enabled ? 10_000 : false,
  })
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
