export type AgentStatus = 'running' | 'completed' | 'failed' | 'stopped'

export type AgentRow = {
  id: string
  description: string
  type: string
  model: string
  effort: string
  status: AgentStatus
  startedAt: number
  endedAt: number | null
  tokens: number
  contextTokens: number
  costUsd: number
}

declare module 'claude-code' {
  interface PluginState {
    'agents-panel': {
      agents: AgentRow[]
      now: number
      lastCostUsd: number
      contextWindow: number
      isCompletedCollapsed: boolean
      hasOpened: boolean
    }
  }
}
