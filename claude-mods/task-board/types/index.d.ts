export type TaskStatus = 'pending' | 'in_progress' | 'completed'

export type BoardTask = { id: string; subject: string; activeForm: string; status: TaskStatus }

declare module 'claude-code' {
  interface PluginState {
    'task-board': { tasks: BoardTask[]; hasOpened: boolean }
  }
}
