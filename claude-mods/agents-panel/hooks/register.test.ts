import { expect, mock, test } from 'claude-code/testing'
import type { On, RenderPropsOf } from 'claude-code'
import type { Engine } from 'claude-code/testing'

import { formatClock, formatCost, formatTokens, mascot, modelLabel, tierLabel } from './register'
import { rasterCells, spritePixels, spriteSvg } from './sprite'

const PANE_PROPS = {
  title: 'Agents', isFocused: false, bodyColumns: 50, placement: 'dock',
  scroll: { offset: 0, bodyRows: 40 }, view: {},
} as unknown as RenderPropsOf['Pane']

test('labels match the panel style', () => {
  expect(modelLabel('claude-opus-5-5')).toBe('Opus 5.5')
  expect(modelLabel('claude-sonnet-5-5-20260101')).toBe('Sonnet 5.5')
  expect(modelLabel('claude-haiku-4-5-20251001')).toBe('Haiku 4.5')
  expect(modelLabel('opus')).toBe('Opus')
  expect(tierLabel('xhigh')).toBe('heavy')
  expect(tierLabel('high')).toBe('careful')
  expect(tierLabel('medium')).toBe('medium')
  expect(tierLabel('low')).toBe('light')
  expect(formatTokens(177_400)).toBe('177k')
  expect(formatTokens(39_000_000)).toBe('39.0M')
  expect(formatCost(1.654)).toBe('$1.65')
  expect(formatCost(14.43)).toBe('$14.4')
  expect(formatClock(201_000)).toBe('3:21')
  expect(formatClock(1_365_000)).toBe('22:45')
})

test('mascots wear a hat per tier and walk while running', () => {
  expect(mascot('heavy', 'running', 0)).toEqual(['▄███▄', '▐•▄•▌', ' ▛ ▜ '])
  expect(mascot('heavy', 'running', 1)[2]).toBe(' ▜ ▛ ')
  expect(mascot('careful', 'completed', 5)).toEqual(['▗▇▇▇▖', '▐•▄•▌', ' ▀ ▀ '])
  expect(mascot('light', 'failed', 0)[1]).toBe('▐x▄x▌')
  const hats = ['light', 'medium', 'careful', 'heavy'].map(t => mascot(t, 'running', 0)[0])
  expect(new Set(hats).size).toBe(4)
  for (const row of mascot('medium', 'stopped', 0)) expect([...row].length).toBe(5)
})

test('pixel sprites differ per tier and theme, walk, sparkle and fade', () => {
  const heavy = spritePixels('heavy', 'running', 0, 'screenshot')
  expect(heavy.length).toBe(12)
  expect(heavy.every(row => row.length === 12)).toBe(true)
  expect(heavy[6]![0]).toBe(0xe8775a)
  expect(spritePixels('heavy', 'running', 0, 'claude')[6]![0]).toBe(0xd97757)
  const hatRows = (t: string) => JSON.stringify(spritePixels(t, 'running', 0, 'screenshot').slice(0, 5))
  expect(new Set(['light', 'medium', 'careful', 'heavy'].map(hatRows)).size).toBe(4)
  expect(JSON.stringify(spritePixels('light', 'running', 1, 'screenshot'))).not.toBe(JSON.stringify(spritePixels('light', 'running', 0, 'screenshot')))
  expect(spritePixels('careful', 'completed', 0, 'screenshot')[2]![0]).not.toBe(-1)
  expect(spritePixels('careful', 'failed', 0, 'screenshot')[6]![0]).not.toBe(0xe8775a)
  const grid = rasterCells(heavy)
  expect([grid.columns, grid.rows]).toEqual([12, 6])
  expect(atob(grid.cells).length).toBe(12 * 6 * 12)
  expect(spriteSvg(heavy)).toContain('fill="#e8775a"')
})

// The engine beneath: a session whose cost grows by `costPerStep` with each model response.
const engine = (on: On, costPerStep: number) => {
  let usd = 1
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 1_000_000 }, rateLimits: [], cost: { usd } } }))
  on('session.start', () => ({ cwd: '/p' }))
  on('command.register', () => ({ value: {} as never }))
  on('ui.open', () => ({ value: {} as never }))
  let n = 0
  on('agent.spawn', () => ({ model: 'claude-opus-5-5', agentId: `agent-${++n}` }))
  on('turn.step', async function* (_, e) {
    usd += costPerStep
    return {
      turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn' as const,
      usage: { input_tokens: 1000, output_tokens: 2000, cache_read_input_tokens: 170_000, cache_creation_input_tokens: 4000, model: e.model },
    }
  })
  on('turn.complete', () => ({ text: '' }))
}

const spawn = ($: Engine, description: string, subagentType = 'general-purpose') =>
  $.agent.spawn({
    tool_use_id: `tu-${description}`, prompt: 'task', description, subagentType,
    provider: { plugin: 'engine', tier: 'core' } as never, parentModel: 'claude-opus-5-5', background: true, fork: false,
  })

const step = async ($: Engine, agentId: string, effort: 'high' | 'xhigh') => {
  const stream = $.turn.step({ turnId: 't', index: 0, model: 'claude-opus-5-5', effort, messageCount: 3, agentId })
  for await (const _ of stream) { /* drain */ }
}

test('agents move from running to completed with their figures', async ($, on) => {
  const clock = mock.clock(on, { now: 1_000 })
  engine(on, 0.5)
  await $.session.start({ cwd: '/p', source: 'startup' } as never)

  await spawn($, 'Cache clock handover')
  await spawn($, 'Stable session prefix', 'Explore')
  await step($, 'agent-1', 'xhigh')
  await step($, 'agent-2', 'high')
  await clock.advance(201_000)
  await $.turn.complete({ turnId: 't', durationMs: 1, answer: '', isAborted: false, reason: 'answer', agentId: 'agent-2' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'agents-panel', surface, component: 'Pane', requestId: 'agents', props: PANE_PROPS })
    expect(await ui.find({ text: /Running · 1/ })).toBeDefined()
    expect(await ui.find({ text: 'Cache clock handover' })).toBeDefined()
    expect(await ui.find({ text: /heavy/ })).toBeDefined()
    expect(await ui.find({ text: /Opus 5\.5 · xhigh/ })).toBeDefined()
    expect(await ui.find({ type: surface === 'terminal' ? 'Raster' : 'Svg' })).toBeDefined()
    expect(await ui.find({ text: /ctx 18% · 175k · ≈\$0\.50 · 3:21/ })).toBeDefined()
    expect(await ui.find({ key: 'toggle-completed', text: /Completed · 1/ })).toBeDefined()
    expect(await ui.find({ text: 'Stable session prefix' })).toBeDefined()
    expect(await ui.find({ text: /≈\$1\.00/ })).toBeDefined()

    await ui.press({ key: 'toggle-completed' })
    expect(await ui.find({ text: 'Stable session prefix' })).toBeUndefined()
    await ui.press({ key: 'toggle-completed' })
    await ui.unmount()
  }
})

test('the simple style keeps the text critters', { options: { mascotColors: 'simple' } }, async ($, on) => {
  mock.clock(on)
  engine(on, 0.1)
  await $.session.start({ cwd: '/p', source: 'startup' } as never)
  await spawn($, 'Server threads')
  await step($, 'agent-1', 'xhigh')
  const ui = await $.ui.mount({ plugin: 'agents-panel', surface: 'terminal', component: 'Pane', requestId: 'agents', props: PANE_PROPS })
  expect(await ui.find({ text: '▄███▄' })).toBeDefined()
  expect(await ui.find({ type: 'Raster' })).toBeUndefined()
  await ui.unmount()
})

test('a failed agent is marked', async ($, on) => {
  mock.clock(on)
  engine(on, 0.1)
  await $.session.start({ cwd: '/p', source: 'startup' } as never)
  await spawn($, 'Server threads')
  await $.turn.complete({ turnId: 't', durationMs: 1, answer: '', isAborted: false, reason: 'error', agentId: 'agent-1' })
  const ui = await $.ui.mount({ plugin: 'agents-panel', surface: 'terminal', component: 'Pane', requestId: 'agents', props: PANE_PROPS })
  expect(await ui.find({ text: /FAILED/ })).toBeDefined()
  expect(await ui.find({ text: /Running · 0/ })).toBeDefined()
  await ui.unmount()
})
