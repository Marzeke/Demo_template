import { expect, mock, test } from 'claude-code/testing'

import { formatDuration, isSlow } from './register'

test('durations read naturally', () => {
  expect(formatDuration(42)).toBe('42s')
  expect(formatDuration(83)).toBe('1m 23s')
  expect(formatDuration(3725)).toBe('1h 02m')
})

test('slow means past the limit, or 4x the usual turn', () => {
  const t = (seconds: number) => ({ seconds, tools: 1, prompt: '', isAborted: false })
  expect(isSlow(301, [], 300)).toBe(true)
  expect(isSlow(200, [t(10), t(20)], 300)).toBe(false)
  expect(isSlow(200, [t(30), t(40), t(45)], 300)).toBe(true)
  expect(isSlow(50, [t(5), t(5), t(5)], 300)).toBe(false)
})

const complete = (turnId: string, durationMs: number) =>
  ({ turnId, durationMs, answer: '', isAborted: false, reason: 'answer' }) as const

test('status shows the last turn, and a slow turn pops up', { options: { slowSeconds: 60 } }, async ($, on) => {
  const clock = mock.clock(on)
  const statuses: (string | undefined)[] = []
  const toasts: string[] = []
  on('ui.status', (_, e) => (statuses.push(e.text), { value: undefined }))
  on('ui.toast', (_, e) => (toasts.push(e.text), { value: undefined }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', () => ({ result: {} as never }))

  await $.turn.start({ text: 'fix the bug', turnId: 't1' })
  expect(statuses.at(-1)).toBe('Working 0s | 0 tool calls')
  await $.tool.call({ tool: 'Read', file_path: '/a' })
  await clock.advance(10_000)
  expect(statuses.at(-1)).toBe('Working 10s | 1 tool call')
  await $.turn.complete(complete('t1', 83_000))
  expect(statuses.at(-1)).toBe('Last turn 1m 23s | 1 tool call')
  expect(toasts).toEqual(['That turn took 1m 23s.'])
})

test('repeated identical calls warn once', { options: { repeatLimit: 3 } }, async ($, on) => {
  mock.clock(on)
  const toasts: string[] = []
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', (_, e) => (toasts.push(e.text), { value: undefined }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('tool.call', () => ({ result: {} as never }))

  await $.turn.start({ text: 'go', turnId: 't1' })
  for (let i = 0; i < 4; i++) await $.tool.call({ tool: 'Bash', command: 'npm test' })
  await $.tool.call({ tool: 'Bash', command: 'npm run lint' })
  expect(toasts.length).toBe(1)
  expect(toasts[0]).toContain('3 times')
  expect(toasts[0]).toContain('npm test')
})
