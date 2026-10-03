export type CostLevel = number

declare module 'claude-code' {
  interface PluginState {
    'usage-meter': { isContextWarned: boolean; costLevel: CostLevel }
  }
}
