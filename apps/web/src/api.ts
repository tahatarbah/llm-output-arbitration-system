import type { ArbitrateBody, ArbitrateResult, ConfigResponse, RunSummary } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export function fetchConfig(): Promise<ConfigResponse> {
  return request<ConfigResponse>('/v1/config')
}

export function runArbitration(body: ArbitrateBody): Promise<ArbitrateResult> {
  return request<ArbitrateResult>('/v1/arbitrate', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listRuns(limit = 50): Promise<RunSummary[]> {
  return request<RunSummary[]>(`/v1/runs?limit=${limit}`)
}

export function getRun(runId: string): Promise<ArbitrateResult> {
  return request<ArbitrateResult>(`/v1/runs/${runId}`)
}
