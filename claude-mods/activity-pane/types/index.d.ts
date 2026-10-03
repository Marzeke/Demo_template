export type ActivityKind = 'changed' | 'read' | 'searched' | 'command' | 'other'

export type ActivityEntry = {
  id: string
  kind: ActivityKind
  label: string
  tool: string
  state: 'running' | 'ok' | 'failed'
}

export type ActivityView = 'files' | 'timeline'

declare module 'claude-code' {
  interface PluginState {
    'activity-pane': { entries: ActivityEntry[]; view: ActivityView; cwd: string }
  }
}
