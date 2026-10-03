export type TurnRecord = { seconds: number; tools: number; prompt: string; isAborted: boolean }

export type LiveTurn = { turnId: string; startedAt: number; prompt: string; tools: number; repeats: Record<string, number>; warned: string[] }

declare module 'claude-code' {
  interface PluginState {
    'turn-timer': { history: TurnRecord[]; live: LiveTurn | null }
  }
}
