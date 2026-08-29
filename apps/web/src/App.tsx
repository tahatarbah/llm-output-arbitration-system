import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchConfig, getRun, listRuns, runArbitration } from './api'
import type { ArbitrateResult, RunSummary } from './types'

const FALLBACK_MODELS = [
  'gpt-4o-mini',
  'gpt-4o',
  'claude-3-5-haiku-latest',
  'claude-sonnet-4-5',
]

const EXAMPLES = [
  {
    label: 'Compare tradeoffs',
    prompt:
      'Compare asyncio and multithreading for a Python web scraper that hits 200 URLs. When would you pick each?',
  },
  {
    label: 'Explain simply',
    prompt: 'Explain CRDTs to a senior engineer in under 200 words, with one concrete example.',
  },
  {
    label: 'Debug advice',
    prompt:
      'A FastAPI endpoint sometimes returns stale data for 2–3 seconds after a write. List the most likely causes and how to verify each.',
  },
]

type ApiStatus = 'checking' | 'online' | 'offline'

export default function App() {
  const [prompt, setPrompt] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [suggested, setSuggested] = useState<string[]>(FALLBACK_MODELS)
  const [selectedGenerators, setSelectedGenerators] = useState<string[]>(['gpt-4o-mini'])
  const [arbiter, setArbiter] = useState('gpt-4o')
  const [customModel, setCustomModel] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [result, setResult] = useState<ArbitrateResult | null>(null)
  const [history, setHistory] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'answer' | 'candidates' | 'meta'>('answer')

  const refreshHistory = useCallback(async () => {
    try {
      const runs = await listRuns()
      setHistory(runs)
    } catch {
      /* ignore */
    }
  }, [])

  const checkApi = useCallback(async () => {
    try {
      const res = await fetch('/health')
      setApiStatus(res.ok ? 'online' : 'offline')
      if (res.ok) {
        await refreshHistory()
      }
    } catch {
      setApiStatus('offline')
    }
  }, [refreshHistory])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await fetch('/health')
        setApiStatus(res.ok ? 'online' : 'offline')
        if (!res.ok) return
        const cfg = await fetchConfig()
        setSuggested(cfg.suggested_models.length ? cfg.suggested_models : FALLBACK_MODELS)
        if (cfg.default_generator_models.length) {
          setSelectedGenerators(cfg.default_generator_models)
        }
        if (cfg.default_arbiter_model) {
          setArbiter(cfg.default_arbiter_model)
        }
        await refreshHistory()
      } catch {
        setApiStatus('offline')
      }
    })()
  }, [refreshHistory])

  const modelOptions = useMemo(() => {
    const set = new Set([...suggested, ...selectedGenerators, arbiter])
    return Array.from(set)
  }, [suggested, selectedGenerators, arbiter])

  function toggleGenerator(model: string) {
    setSelectedGenerators((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model],
    )
  }

  function addCustomModel() {
    const m = customModel.trim()
    if (!m) return
    if (!selectedGenerators.includes(m)) {
      setSelectedGenerators((prev) => [...prev, m])
    }
    if (!modelOptions.includes(m)) {
      setSuggested((prev) => [...prev, m])
    }
    setCustomModel('')
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!prompt.trim() || selectedGenerators.length === 0) return
    setLoading(true)
    setError(null)
    setActiveTab('answer')
    try {
      const data = await runArbitration({
        prompt: prompt.trim(),
        generator_models: selectedGenerators,
        arbiter_model: arbiter,
        system_prompt: systemPrompt.trim() || undefined,
        temperature,
        persist: true,
      })
      setResult(data)
      await refreshHistory()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  async function openRun(runId: string) {
    setLoading(true)
    setError(null)
    try {
      const data = await getRun(runId)
      setResult(data)
      setPrompt(data.prompt)
      setSelectedGenerators(data.generator_models)
      setArbiter(data.arbiter_model)
      setSystemPrompt(data.system_prompt ?? '')
      setActiveTab('answer')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  async function copyAnswer() {
    if (!result?.final_answer) return
    await navigator.clipboard.writeText(result.final_answer)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  function downloadJson() {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `arbitration-${result.run_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-copy">
          <p className="brand">LLM Arbitration</p>
          <h1>Synthesize one answer from many models</h1>
          <p className="lede">
            Generators answer in parallel. An arbiter merges the strongest parts, records conflicts,
            and attributes contributions.
          </p>
        </div>
        <div className={`api-pill ${apiStatus}`}>
          <span className="dot" />
          {apiStatus === 'checking' && 'Checking API…'}
          {apiStatus === 'online' && 'API online'}
          {apiStatus === 'offline' && (
            <>
              API offline{' '}
              <button type="button" className="linkish" onClick={() => void checkApi()}>
                retry
              </button>
            </>
          )}
        </div>
      </header>

      <div className="workspace">
        <aside className="rail">
          <div className="rail-head">
            <h2>History</h2>
            <button type="button" className="ghost tiny" onClick={() => void refreshHistory()}>
              Refresh
            </button>
          </div>
          {history.length === 0 ? (
            <p className="muted small">Saved runs appear here after you arbitrate.</p>
          ) : (
            <ul className="hist-list">
              {history.map((run) => (
                <li key={run.run_id}>
                  <button
                    type="button"
                    className={result?.run_id === run.run_id ? 'hist on' : 'hist'}
                    onClick={() => void openRun(run.run_id)}
                  >
                    <span className="hist-prompt">{run.prompt}</span>
                    <span className="hist-meta">
                      {new Date(run.created_at).toLocaleString()} · {run.arbiter_model}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="main">
          <form className="compose" onSubmit={(e) => void onSubmit(e)}>
            <div className="examples">
              <span className="muted small">Try</span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.label}
                  type="button"
                  className="ghost tiny"
                  onClick={() => setPrompt(ex.prompt)}
                >
                  {ex.label}
                </button>
              ))}
            </div>

            <label>
              Prompt
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={5}
                placeholder="Ask something you want multiple models to answer…"
                required
              />
            </label>

            <details className="advanced">
              <summary>System prompt &amp; temperature</summary>
              <label>
                System prompt
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  rows={2}
                  placeholder="Shared instructions for all generators"
                />
              </label>
              <label className="temp">
                <span>
                  Temperature <strong>{temperature.toFixed(1)}</strong>
                </span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.1}
                  value={temperature}
                  onChange={(e) => setTemperature(Number(e.target.value))}
                />
              </label>
            </details>

            <fieldset>
              <legend>Generators</legend>
              <div className="chips">
                {modelOptions.map((model) => (
                  <label
                    key={model}
                    className={`chip ${selectedGenerators.includes(model) ? 'on' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedGenerators.includes(model)}
                      onChange={() => toggleGenerator(model)}
                    />
                    {model}
                  </label>
                ))}
              </div>
              <div className="add-row">
                <input
                  type="text"
                  value={customModel}
                  onChange={(e) => setCustomModel(e.target.value)}
                  placeholder="Add model id (OpenAI or Claude)"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addCustomModel()
                    }
                  }}
                />
                <button type="button" className="ghost" onClick={addCustomModel}>
                  Add
                </button>
              </div>
            </fieldset>

            <div className="row-2">
              <label>
                Arbiter
                <select value={arbiter} onChange={(e) => setArbiter(e.target.value)}>
                  {modelOptions.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>
              <div className="actions">
                <button
                  type="submit"
                  disabled={
                    loading || apiStatus !== 'online' || !prompt.trim() || selectedGenerators.length === 0
                  }
                >
                  {loading ? 'Arbitrating…' : 'Run arbitration'}
                </button>
              </div>
            </div>
          </form>

          {error && <p className="error">{error}</p>}

          {loading && (
            <div className="pipeline" aria-live="polite">
              <div className="step on">1 · Fan-out generators</div>
              <div className="step on pulse">2 · Arbiter synthesizes</div>
              <div className="step">3 · Persist &amp; display</div>
            </div>
          )}

          {!result && !loading && (
            <section className="empty">
              <h2>No run yet</h2>
              <p className="muted">
                Pick generators, choose an arbiter, and run. You will see the merged answer,
                conflicts, attributions, and each raw candidate.
              </p>
            </section>
          )}

          {result && (
            <section className="result">
              <div className="result-head">
                <div>
                  <h2>Result</h2>
                  <code className="run-id">{result.run_id}</code>
                </div>
                <div className="result-actions">
                  <button type="button" className="ghost tiny" onClick={() => void copyAnswer()}>
                    {copied ? 'Copied' : 'Copy answer'}
                  </button>
                  <button type="button" className="ghost tiny" onClick={downloadJson}>
                    Download JSON
                  </button>
                </div>
              </div>

              <div className="tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  className={activeTab === 'answer' ? 'on' : ''}
                  onClick={() => setActiveTab('answer')}
                >
                  Synthesized
                </button>
                <button
                  type="button"
                  role="tab"
                  className={activeTab === 'candidates' ? 'on' : ''}
                  onClick={() => setActiveTab('candidates')}
                >
                  Candidates ({result.candidates.length})
                </button>
                <button
                  type="button"
                  role="tab"
                  className={activeTab === 'meta' ? 'on' : ''}
                  onClick={() => setActiveTab('meta')}
                >
                  Conflicts &amp; usage
                </button>
              </div>

              {activeTab === 'answer' && (
                <article className="final">{result.final_answer || '_(empty)_'}</article>
              )}

              {activeTab === 'candidates' && (
                <div className="candidates">
                  {result.candidates.map((c) => (
                    <article key={c.model} className={c.error ? 'cand err' : 'cand'}>
                      <header>
                        <strong>{c.model}</strong>
                        <span>{c.error ? 'failed' : `${Math.round(c.latency_ms)} ms`}</span>
                      </header>
                      <pre>{c.error ? c.error : c.content || '_(empty)_'}</pre>
                    </article>
                  ))}
                </div>
              )}

              {activeTab === 'meta' && (
                <div className="meta-grid">
                  <div>
                    <h3>Conflicts</h3>
                    {result.conflicts.length === 0 ? (
                      <p className="muted">No conflicts reported.</p>
                    ) : (
                      <ul>
                        {result.conflicts.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <h3>Attributions</h3>
                    {result.attributions.length === 0 ? (
                      <p className="muted">No attributions.</p>
                    ) : (
                      <ul>
                        {result.attributions.map((a) => (
                          <li key={`${a.model}-${a.contribution}`}>
                            <strong>{a.model}</strong> — {a.contribution}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <p className="usage">
                    Tokens {result.usage.total_tokens} (prompt {result.usage.prompt_tokens} ·
                    completion {result.usage.completion_tokens}) · arbiter {result.arbiter_model}
                    {typeof result.meta.arbiter_latency_ms === 'number' &&
                      ` · arbiter ${Math.round(result.meta.arbiter_latency_ms as number)} ms`}
                  </p>
                </div>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  )
}
