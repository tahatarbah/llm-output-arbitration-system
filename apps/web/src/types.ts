export type TokenUsage = {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export type CandidateResult = {
  model: string
  content: string | null
  latency_ms: number
  usage: TokenUsage
  error: string | null
}

export type Attribution = {
  model: string
  contribution: string
}

export type ArbitrateResult = {
  run_id: string
  prompt: string
  system_prompt: string | null
  generator_models: string[]
  arbiter_model: string
  final_answer: string
  conflicts: string[]
  attributions: Attribution[]
  candidates: CandidateResult[]
  usage: TokenUsage
  created_at: string
  meta: Record<string, unknown>
}

export type RunSummary = {
  run_id: string
  prompt: string
  arbiter_model: string
  generator_models: string[]
  created_at: string
  final_answer_preview: string
}

export type ConfigResponse = {
  default_generator_models: string[]
  default_arbiter_model: string
  suggested_models: string[]
}

export type ArbitrateBody = {
  prompt: string
  generator_models: string[]
  arbiter_model: string
  system_prompt?: string
  temperature?: number
  persist?: boolean
}
