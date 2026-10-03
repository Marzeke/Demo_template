import { expect, test } from 'claude-code/testing'
import type { SessionMeasureInput } from 'claude-code'

const measure = (tokens: number, usd: number): SessionMeasureInput => ({
  context: { tokens, window: 1_000_000, percent: Math.round(tokens / 10_000) },
  rateLimits: [],
  cost: { usd },
  changed: ['context', 'cost'],
})

test('status line shows context and cost', async ($, on) => {
  const statuses: (string | undefined)[] = []
  on('ui.status', (_, e) => (statuses.push(e.text), { value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  await $.session.measure(measure(123_400, 4.5))
  expect(statuses.at(-1)).toBe('Context 123k/1M (12%) | $4.50 this session')
})

test('context warns once, re-arms after dropping below', { options: { contextWarnTokens: 300000, costWarnUsd: 1000 } }, async ($, on) => {
  const toasts: string[] = []
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', (_, e) => (toasts.push(e.text), { value: undefined }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  await $.session.measure(measure(250_000, 1))
  expect(toasts.length).toBe(0)
  await $.session.measure(measure(310_000, 1))
  await $.session.measure(measure(320_000, 1))
  expect(toasts.length).toBe(1)
  expect(toasts[0]).toContain('310k')
  await $.session.measure(measure(40_000, 1))
  await $.session.measure(measure(305_000, 1))
  expect(toasts.length).toBe(2)
})

test('cost warns at first threshold then every step', { options: { costWarnUsd: 50, costStepUsd: 50, contextWarnTokens: 900000 } }, async ($, on) => {
  const toasts: string[] = []
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', (_, e) => (toasts.push(e.text), { value: undefined }))
  on('session.measure', (_, e) => ({ changed: e.changed }))

  for (const usd of [10, 49, 51, 60, 99, 101, 250]) await $.session.measure(measure(1000, usd))
  expect(toasts).toEqual([
    'This session has cost $51.00 so far.',
    'This session has cost $101.00 so far.',
    'This session has cost $250.00 so far.',
  ])
})
