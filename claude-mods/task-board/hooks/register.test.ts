import { expect, test } from 'claude-code/testing'
import type { RenderPropsOf } from 'claude-code'

import { applyCall, progressBar, summary } from './register'

const PANE_PROPS = {
  title: 'Tasks', isFocused: false, bodyColumns: 50, placement: 'dock',
  scroll: { offset: 0, bodyRows: 30 }, view: {},
} as unknown as RenderPropsOf['Pane']

test('task tools build the board', () => {
  let list = applyCall([], 'TaskCreate', { subject: 'Write tests', activeForm: 'Writing tests' }, { task: { id: '1', subject: 'Write tests' } })
  list = applyCall(list, 'TaskCreate', { subject: 'Ship it' }, { task: { id: '2', subject: 'Ship it' } })
  list = applyCall(list, 'TaskUpdate', { taskId: '1', status: 'in_progress' }, {})
  expect(summary(list)).toBe('Tasks 0/2 | Writing tests')
  list = applyCall(list, 'TaskUpdate', { taskId: '1', status: 'completed' }, {})
  list = applyCall(list, 'TaskUpdate', { taskId: '2', status: 'deleted' }, {})
  expect(summary(list)).toBe('Tasks 1/1 done')
})

test('TodoWrite replaces the list', () => {
  const list = applyCall([], 'TodoWrite', {
    todos: [
      { content: 'a', status: 'completed', activeForm: 'A' },
      { content: 'b', status: 'in_progress', activeForm: 'Doing b' },
    ],
  }, {})
  expect(summary(list)).toBe('Tasks 1/2 | Doing b')
  expect(progressBar(1, 2, 10)).toBe('[#####-----]')
})

test('board pane draws progress and tasks', async ($, on) => {
  const statuses: (string | undefined)[] = []
  on('ui.status', (_, e) => (statuses.push(e.text), { value: undefined }))
  on('ui.open', () => ({ value: { id: 'task-board' } as never }))
  let next = 1
  on('tool.call', (_, e) =>
    String(e.tool) === 'TaskCreate' ? { result: { task: { id: String(next++), subject: '' } } as never } : { result: { success: true } as never },
  )

  await $.tool.call({ tool: 'TaskCreate', subject: 'Plan', description: 'x', activeForm: 'Planning' })
  await $.tool.call({ tool: 'TaskCreate', subject: 'Build', description: 'x' })
  await $.tool.call({ tool: 'TaskUpdate', taskId: '1', status: 'completed' })
  await $.tool.call({ tool: 'TaskUpdate', taskId: '2', status: 'in_progress' })
  expect(statuses.at(-1)).toBe('Tasks 1/2 | Build')

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'task-board', surface, component: 'Pane', requestId: 'task-board', props: PANE_PROPS })
    expect(await ui.find({ text: /1\/2/ })).toBeDefined()
    expect(await ui.find({ text: /\[x\] Plan/ })).toBeDefined()
    expect(await ui.find({ text: /\[>\] Build/ })).toBeDefined()
    await ui.unmount()
  }
})
