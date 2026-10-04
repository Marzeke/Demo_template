import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelUsage, Register } from 'claude-code'

import type { AgentRow, AgentStatus } from '../types'

import { rasterCells, spritePixels, spriteSvg } from './sprite'
import type { MascotTheme } from './sprite'

const PANE = 'agents'
const ACCENT = '#4B87E0'
const LIGHT = '#BCDBEC'

const agents = atom({ plugin: 'agents-panel', key: 'agents' } as const, [])
const now = atom({ plugin: 'agents-panel', key: 'now' } as const, 0)
const lastCostUsd = atom({ plugin: 'agents-panel', key: 'lastCostUsd' } as const, -1)
const contextWindow = atom({ plugin: 'agents-panel', key: 'contextWindow' } as const, 0)
const isCompletedCollapsed = atom({ plugin: 'agents-panel', key: 'isCompletedCollapsed' } as const, false)
const hasOpened = atom({ plugin: 'agents-panel', key: 'hasOpened' } as const, false)

// "claude-opus-5-5" -> "Opus 5.5"; aliases and unknown ids pass through tidied.
export const modelLabel = (model: string): string => {
  const m = /claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?/i.exec(model)
  if (!m || !m[1] || !m[2]) return model ? model.charAt(0).toUpperCase() + model.slice(1) : ''
  const family = m[1].charAt(0).toUpperCase() + m[1].slice(1)

  return m[3] ? `${family} ${m[2]}.${m[3]}` : `${family} ${m[2]}`
}

// The tier word shown in front of the model, from the effort the agent's requests ask for.
export const tierLabel = (effort: string): string => {
  switch (effort) {
    case 'low':
      return 'light'
    case 'medium':
      return 'medium'
    case 'high':
      return 'careful'
    case 'xhigh':
    case 'max':
      return 'heavy'
    default:
      return effort ? 'custom' : ''
  }
}

export const formatTokens = (n: number): string =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`

export const formatClock = (ms: number): string => {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(h ? 2 : 1, '0')
  const ss = String(s % 60).padStart(2, '0')

  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export const formatCost = (usd: number): string => (usd >= 10 ? `$${usd.toFixed(1)}` : `$${usd.toFixed(2)}`)

const totalTokens = (u: ModelUsage): number =>
  u.input_tokens + u.output_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens

const inputSide = (u: ModelUsage): number => u.input_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens

// Hats tell the tiers apart by shape, so they read in any theme and colour scheme.
const HATS: Record<string, string> = {
  light: '  ▂  ',
  medium: ' ▄▄▄ ',
  careful: '▗▇▇▇▖',
  heavy: '▄███▄',
  custom: ' ▄▄▄ ',
  '': '     ',
}

// A three-row critter: hat for the tier, a face, and legs that walk while the agent runs.
export const mascot = (tier: string, status: AgentStatus, frame: number): [string, string, string] => {
  const hat = HATS[tier] ?? HATS['']!
  const face = status === 'failed' ? '▐x▄x▌' : status === 'stopped' ? '▐-▄-▌' : '▐•▄•▌'
  const legs = status === 'running' ? (frame % 2 === 0 ? ' ▛ ▜ ' : ' ▜ ▛ ') : ' ▀ ▀ '

  return [hat, face, legs]
}

const newRow = (id: string, startedAt: number, fields: Partial<AgentRow> = {}): AgentRow => ({
  id,
  description: `Agent ${id.slice(0, 6)}`,
  type: '',
  model: '',
  effort: '',
  status: 'running',
  startedAt,
  endedAt: null,
  tokens: 0,
  contextTokens: 0,
  costUsd: 0,
  ...fields,
})

const upsert = (list: readonly AgentRow[], id: string, make: () => AgentRow, change: (row: AgentRow) => AgentRow): AgentRow[] =>
  list.some(r => r.id === id) ? list.map(r => (r.id === id ? change(r) : r)) : [...list, change(make())]

let ticker: { cancel: () => void } | undefined

// Keeps the running agents' clocks moving: ticks once a second while any agent runs.
async function syncTicker($: EngineInterface): Promise<void> {
  const isAnyRunning = (await read($, agents)).some(r => r.status === 'running')
  if (isAnyRunning && !ticker) {
    ticker = $.clock.every(1000, () => void tick($))
  } else if (!isAnyRunning && ticker) {
    ticker.cancel()
    ticker = undefined
  }
}

async function tick($: EngineInterface): Promise<void> {
  const t = await $.clock.now()
  await update($, now, () => t)
}

async function maybeOpen($: EngineInterface, autoOpen: boolean): Promise<void> {
  if (autoOpen && !(await read($, hasOpened))) {
    await update($, hasOpened, () => true)
    void $.ui.open({ id: PANE, title: 'Agents' })
  }
}

// Attributes the growth in the session's cost since the last reading to the loop that just answered.
async function costDelta($: EngineInterface): Promise<number> {
  const usd = (await $.session.usage()).cost?.usd
  if (usd === undefined) return 0
  const last = await read($, lastCostUsd)
  await update($, lastCostUsd, () => usd)

  return last < 0 ? 0 : Math.max(0, usd - last)
}

export const register: Register = (on, options) => {
  const autoOpen = options.autoOpen !== false
  const mascotStyle = String(options.mascotColors ?? 'screenshot')
  const theme: MascotTheme = mascotStyle === 'claude' ? 'claude' : 'screenshot'
  ticker = undefined

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    await $.command.register({ name: 'agent-panel', description: 'Show the agents panel' })
    const usage = await $.session.usage()
    await update($, contextWindow, () => usage.context.window)
    await update($, lastCostUsd, () => usage.cost?.usd ?? -1)
    const startedAt = await $.clock.now()
    await update($, now, () => startedAt)
    await syncTicker($)

    return ran
  })

  on('command.run', { command: 'agent-panel' }, async $ => {
    await update($, hasOpened, () => true)
    await $.ui.open({ id: PANE, title: 'Agents' })

    return { text: 'Agents panel opened.' }
  })

  on('agent.spawn', async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || !ran.agentId) return ran

    const id = ran.agentId
    const t = await $.clock.now()
    await update($, agents, list =>
      upsert(list, id, () => newRow(id, t), row => ({
        ...row,
        description: e.description || row.description,
        type: e.subagentType,
        model: ran.model || row.model,
        status: 'running',
        endedAt: null,
      })),
    )
    await update($, now, () => t)
    await syncTicker($)
    await maybeOpen($, autoOpen)

    return ran
  })

  // Agents started some other way (a workflow's) show up when they first use a tool.
  on('tool.call', async ($, e, next) => {
    if (e.agentId !== undefined) {
      const id = e.agentId
      const list = await read($, agents)
      if (!list.some(r => r.id === id)) {
        const t = await $.clock.now()
        await update($, agents, l => upsert(l, id, () => newRow(id, t), row => row))
        await syncTicker($)
        await maybeOpen($, autoOpen)
      }
    }

    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    const result = yield* next(e)

    const delta = await costDelta($)
    if (e.agentId === undefined) return result

    const id = e.agentId
    const usage = result.usage
    const effort = typeof e.effort === 'string' ? e.effort : e.effort === undefined ? '' : 'custom'
    const t = await $.clock.now()
    const known = (await read($, agents)).some(r => r.id === id)
    if (!known) return result

    await update($, agents, list =>
      upsert(list, id, () => newRow(id, t), row => ({
        ...row,
        model: e.model || row.model,
        effort: effort || row.effort,
        status: 'running',
        endedAt: null,
        tokens: row.tokens + (usage ? totalTokens(usage) : 0),
        contextTokens: usage ? inputSide(usage) : row.contextTokens,
        costUsd: row.costUsd + delta,
      })),
    )
    await syncTicker($)

    return result
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) {
      const id = e.agentId
      const status: AgentStatus = e.reason === 'error' ? 'failed' : e.isAborted ? 'stopped' : 'completed'
      const t = await $.clock.now()
      await update($, agents, list => list.map(r => (r.id === id ? { ...r, status, endedAt: t } : r)))
      await update($, now, () => t)
      await syncTicker($)
    }

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Text, Button } = elements
    const list = await read($, agents)
    const t = Math.max(await read($, now), ...list.map(r => r.endedAt ?? 0))
    const window = (await read($, contextWindow)) || 200_000
    const isCollapsed = await read($, isCompletedCollapsed)
    const width = Math.max(20, (e.props.bodyColumns || 40) - 2)
    const barWidth = Math.max(10, width - (e.surface === 'terminal' ? 20 : 10))

    if (list.length === 0) {
      return <Text dimColor>No agents yet. Subagents appear here as soon as Claude starts one.</Text>
    }

    const running = list.filter(r => r.status === 'running')
    const finished = list.filter(r => r.status !== 'running')
    const cost = list.reduce((sum, r) => sum + r.costUsd, 0)
    const tokens = list.reduce((sum, r) => sum + r.tokens, 0)
    const firstStart = Math.min(...list.map(r => r.startedAt))
    const lastEnd = running.length ? t : Math.max(...list.map(r => r.endedAt ?? r.startedAt))

    const stat = (key: string, label: string, value: string) => (
      <Box key={key} flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={1} flexGrow={1}>
        <Text dimColor>{label}</Text>
        <Text bold>{value}</Text>
      </Box>
    )

    // The pixel critter where the surface can draw one; undefined falls back to the text critter.
    const frame = Math.floor(t / 1000)
    const sprite = (r: AgentRow, tier: string) => {
      if (mascotStyle === 'simple') return undefined
      const pixels = spritePixels(tier, r.status, frame, theme)
      const alt = `${tier || 'agent'} mascot, ${r.status}`
      // Raster draws only on the terminal (other surfaces list it but draw nothing).
      if (e.surface === 'terminal' && 'Raster' in elements) {
        const { Raster } = elements
        const grid = rasterCells(pixels)

        return (
          <Box flexDirection="column" width={17} flexShrink={0}>
            <Raster key={`m-${r.id}`} columns={grid.columns} rows={grid.rows} cells={grid.cells} />
          </Box>
        )
      }
      if ('Svg' in elements) {
        const { Svg } = elements

        return (
          <Box flexDirection="column" width={7} flexShrink={0}>
            <Svg source={spriteSvg(pixels)} alt={alt} width={48} height={48} />
          </Box>
        )
      }

      return undefined
    }

    const card = (r: AgentRow) => {
      const pct = Math.min(100, Math.round((r.contextTokens / window) * 100))
      const filled = Math.round((pct / 100) * barWidth)
      const elapsed = formatClock((r.endedAt ?? t) - r.startedAt)
      const mark = r.status === 'completed' ? 'done' : r.status === 'failed' ? 'FAILED' : r.status === 'stopped' ? 'stopped' : 'live'
      const tier = tierLabel(r.effort)
      const meta = [modelLabel(r.model), r.effort].filter(Boolean).join(' · ')

      const [hat, face, legs] = mascot(tier, r.status, Math.floor(t / 1000))
      const body = r.status === 'running' ? ACCENT : r.status === 'completed' ? LIGHT : undefined

      return (
        <Box key={r.id} flexDirection="row" marginBottom={1}>
          {sprite(r, tier) ?? (
            <Box flexDirection="column" width={6} flexShrink={0}>
              <Text bold>{hat}</Text>
              <Text color={body} dimColor={r.status === 'stopped'}>{face}</Text>
              <Text color={body} dimColor={r.status === 'stopped'}>{legs}</Text>
            </Box>
          )}
          <Box flexDirection="column" flexGrow={1}>
            <Box flexDirection="row" justifyContent="space-between">
              <Text bold wrap="truncate-end">{r.description}</Text>
              <Text color={r.status === 'running' ? ACCENT : undefined} bold={r.status === 'failed'} dimColor={r.status === 'completed'}>
                {' '}{mark}
              </Text>
            </Box>
            <Text wrap="truncate-end">
              {tier ? <Text color={ACCENT} bold={tier === 'heavy'}>{tier} </Text> : ''}
              <Text dimColor>{meta || r.type || 'starting...'}</Text>
            </Text>
            <Text dimColor wrap="truncate-end">
              ctx {pct}% · {formatTokens(r.contextTokens)} · ≈{formatCost(r.costUsd)} · {elapsed}
            </Text>
            <Text>
              <Text color={r.status === 'running' ? ACCENT : LIGHT}>{'━'.repeat(filled)}</Text>
              <Text dimColor>{'─'.repeat(barWidth - filled)}</Text>
            </Text>
          </Box>
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1}>
          {stat('cost', 'Cost', `≈${formatCost(cost)}`)}
          {stat('tokens', 'Tokens', formatTokens(tokens))}
          {stat('time', 'Time', formatClock(lastEnd - firstStart))}
        </Box>
        <Text> </Text>
        <Text bold color={ACCENT}>Running · {running.length}</Text>
        {running.length === 0 && <Text dimColor>  nothing running</Text>}
        {running.map(card)}
        {finished.length > 0 && (
          <Button
            key="toggle-completed"
            label={`${isCollapsed ? '▸' : '▾'} Completed · ${finished.length}`}
            onPress={() => update($, isCompletedCollapsed, c => !c)}
          />
        )}
        {!isCollapsed && finished.slice().reverse().map(card)}
      </Box>
    )
  })
}
