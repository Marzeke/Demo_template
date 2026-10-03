import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { BoardTask, TaskStatus } from '../types'

const PANE = 'task-board'
const ACCENT = '#4B87E0'

const tasks = atom({ plugin: 'task-board', key: 'tasks' } as const, [])
const hasOpened = atom({ plugin: 'task-board', key: 'hasOpened' } as const, false)

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}

const str = (value: unknown): string => (typeof value === 'string' ? value : '')

const isStatus = (value: unknown): value is TaskStatus =>
  value === 'pending' || value === 'in_progress' || value === 'completed'

export const progressBar = (done: number, total: number, width = 20): string => {
  const filled = total === 0 ? 0 : Math.round((done / total) * width)

  return `[${'#'.repeat(filled)}${'-'.repeat(width - filled)}]`
}

export const summary = (list: readonly BoardTask[]): string | undefined => {
  if (list.length === 0) return undefined
  const done = list.filter(t => t.status === 'completed').length
  const active = list.find(t => t.status === 'in_progress')
  if (done === list.length) return `Tasks ${done}/${list.length} done`

  return `Tasks ${done}/${list.length}${active ? ` | ${active.activeForm || active.subject}` : ''}`
}

// Applies one task-tool call and its result to the board.
export const applyCall = (list: readonly BoardTask[], tool: string, args: Record<string, unknown>, result: unknown): BoardTask[] => {
  const out = asRecord(result)
  switch (tool) {
    case 'TaskCreate': {
      const id = str(asRecord(out.task).id)
      if (!id) return [...list]
      const task: BoardTask = { id, subject: str(args.subject), activeForm: str(args.activeForm), status: 'pending' }

      return [...list.filter(t => t.id !== id), task]
    }
    case 'TaskUpdate': {
      const id = str(args.taskId)
      if (args.status === 'deleted') return list.filter(t => t.id !== id)

      return list.map(t =>
        t.id === id
          ? {
              ...t,
              subject: str(args.subject) || t.subject,
              activeForm: str(args.activeForm) || t.activeForm,
              status: isStatus(args.status) ? args.status : t.status,
            }
          : t,
      )
    }
    case 'TaskList': {
      const rows = Array.isArray(out.tasks) ? out.tasks.map(asRecord) : []
      const known = new Map(list.map(t => [t.id, t]))

      return rows.map(row => {
        const id = str(row.id)
        const status = isStatus(row.status) ? row.status : 'pending'

        return { id, subject: str(row.subject), activeForm: known.get(id)?.activeForm ?? '', status }
      })
    }
    case 'TodoWrite': {
      const todos = Array.isArray(args.todos) ? args.todos.map(asRecord) : []

      return todos.map((todo, i) => ({
        id: `todo-${i}`,
        subject: str(todo.content),
        activeForm: str(todo.activeForm),
        status: isStatus(todo.status) ? todo.status : 'pending',
      }))
    }
    default:
      return [...list]
  }
}

const TASK_TOOLS = ['TaskCreate', 'TaskUpdate', 'TaskList', 'TodoWrite']

async function refresh($: EngineInterface, autoOpen: boolean): Promise<void> {
  const list = await read($, tasks)
  $.ui.status(summary(list))
  if (autoOpen && list.length > 0 && !(await read($, hasOpened))) {
    await update($, hasOpened, () => true)
    void $.ui.open({ id: PANE, title: 'Tasks' })
  }
}

export const register: Register = (on, options) => {
  const autoOpen = options.autoOpen !== false

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    await $.command.register({ name: 'tasks', description: "Show Claude's task board" })
    $.ui.status(summary(await read($, tasks)))

    return ran
  })

  on('command.run', { command: 'tasks' }, async $ => {
    await update($, hasOpened, () => true)
    await $.ui.open({ id: PANE, title: 'Tasks' })

    return { text: 'Task board opened.' }
  })

  on('tool.call', async ($, e, next) => {
    const tool = String(e.tool)
    if (!TASK_TOOLS.includes(tool)) return next(e)

    const ran = await next(e)
    if (ran.deny === undefined && ran.isError !== true) {
      const args = e as unknown as Record<string, unknown>
      await update($, tasks, list => applyCall(list, tool, args, ran.result))
      await refresh($, autoOpen)
    }

    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, tasks)

    if (list.length === 0) {
      return <Text dimColor>No tasks yet. Claude's task list appears here when it plans multi-step work.</Text>
    }

    const done = list.filter(t => t.status === 'completed').length
    const width = Math.max(10, Math.min(30, (e.viewport?.columns ?? 40) - 14))

    return (
      <Box flexDirection="column">
        <Text bold color={ACCENT}>
          {progressBar(done, list.length, width)} {done}/{list.length}
        </Text>
        <Text> </Text>
        {list.map(task => (
          <Text
            key={task.id}
            wrap="wrap"
            bold={task.status === 'in_progress'}
            color={task.status === 'in_progress' ? ACCENT : undefined}
            dimColor={task.status === 'completed'}
          >
            {task.status === 'completed' ? '[x]' : task.status === 'in_progress' ? '[>]' : '[ ]'}{' '}
            {task.status === 'in_progress' && task.activeForm ? task.activeForm : task.subject}
          </Text>
        ))}
      </Box>
    )
  })
}
