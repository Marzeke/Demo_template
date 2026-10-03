import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, ToolCallInput } from 'claude-code'

import type { LiveTurn, TurnRecord } from '../types'

const history = atom({ plugin: 'turn-timer', key: 'history' } as const, [])
const live = atom({ plugin: 'turn-timer', key: 'live' } as const, null)

const TICK_MS = 5000
const WARN_MS = 10000

export const formatDuration = (seconds: number): string => {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`

  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

const median = (values: readonly number[]): number => {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)

  return sorted.length % 2 ? (sorted[mid] ?? 0) : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2
}

// A turn is slow when it passes the fixed limit, or (with enough history) runs 4x the usual length and over a minute.
export const isSlow = (seconds: number, past: readonly TurnRecord[], slowSeconds: number): boolean => {
  if (seconds >= slowSeconds) return true
  const done = past.filter(t => !t.isAborted).map(t => t.seconds)
  if (done.length < 3) return false

  return seconds >= 60 && seconds >= 4 * median(done)
}

// What makes two tool calls "the same": the tool and its arguments.
export const callKey = (e: ToolCallInput): string => {
  const { tool_use_id: _id, agentId: _agent, ...args } = e as unknown as Record<string, unknown>

  return JSON.stringify(args)
}

const describeCall = (e: ToolCallInput): string => {
  const args = e as unknown as Record<string, unknown>
  const detail = args.command ?? args.file_path ?? args.pattern ?? ''
  const text = `${String(e.tool)} ${typeof detail === 'string' ? detail : ''}`.replace(/\s+/g, ' ').trim()

  return text.length > 60 ? `${text.slice(0, 57)}...` : text
}

const liveStatus = (turn: LiveTurn, now: number): string =>
  `Working ${formatDuration((now - turn.startedAt) / 1000)} | ${turn.tools} tool call${turn.tools === 1 ? '' : 's'}`

async function tick($: EngineInterface): Promise<void> {
  const turn = await read($, live)
  if (turn) $.ui.status(liveStatus(turn, await $.clock.now()))
}

export const register: Register = (on, options) => {
  const slowSeconds = Number(options.slowSeconds ?? 300)
  const repeatLimit = Math.max(2, Number(options.repeatLimit ?? 3))
  let ticker: { cancel: () => void } | undefined

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    await $.command.register({ name: 'turns', description: 'Show how long recent turns took' })
    // A reload mid-turn leaves the turn in state; restart its ticker.
    if (await read($, live)) ticker = $.clock.every(TICK_MS, () => void tick($))

    return ran
  })

  on('turn.start', async ($, e, next) => {
    const startedAt = await $.clock.now()
    const turn: LiveTurn = { turnId: e.turnId, startedAt, prompt: e.text.slice(0, 80), tools: 0, repeats: {}, warned: [] }
    await update($, live, () => turn)
    $.ui.status(liveStatus(turn, startedAt))
    ticker?.cancel()
    ticker = $.clock.every(TICK_MS, () => void tick($))

    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const turn = await read($, live)
    if (turn && e.agentId === undefined) {
      const key = callKey(e)
      const times = (turn.repeats[key] ?? 0) + 1
      const shouldWarn = times >= repeatLimit && !turn.warned.includes(key)
      await update($, live, t =>
        t && t.turnId === turn.turnId
          ? { ...t, tools: t.tools + 1, repeats: { ...t.repeats, [key]: times }, warned: shouldWarn ? [...t.warned, key] : t.warned }
          : t,
      )
      if (shouldWarn) {
        $.ui.toast(`Claude has run the same call ${times} times this turn (${describeCall(e)}). It may be going in circles.`, {
          timeoutMs: WARN_MS,
        })
      }
    } else if (turn) {
      await update($, live, t => (t ? { ...t, tools: t.tools + 1 } : t))
    }

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)

    ticker?.cancel()
    ticker = undefined
    const turn = await read($, live)
    await update($, live, () => null)
    const seconds = e.durationMs / 1000
    const record: TurnRecord = { seconds, tools: turn?.tools ?? 0, prompt: turn?.prompt ?? '', isAborted: e.isAborted }
    const past = await read($, history)
    await update($, history, list => [...list, record].slice(-100))

    const tools = `${record.tools} tool call${record.tools === 1 ? '' : 's'}`
    $.ui.status(`Last turn ${formatDuration(seconds)} | ${tools}${e.isAborted ? ' (interrupted)' : ''}`)

    if (!e.isAborted && isSlow(seconds, past, slowSeconds)) {
      const done = past.filter(t => !t.isAborted)
      const usual = done.length >= 3 ? ` (usually about ${formatDuration(median(done.map(t => t.seconds)))})` : ''
      $.ui.toast(`That turn took ${formatDuration(seconds)}${usual}.`, { timeoutMs: WARN_MS })
    }

    return next(e)
  })

  on('command.run', { command: 'turns' }, async $ => {
    const list = await read($, history)
    if (list.length === 0) return { text: 'No turns timed yet this session.' }

    const done = list.filter(t => !t.isAborted)
    const total = list.reduce((sum, t) => sum + t.seconds, 0)
    const lines = list
      .slice(-10)
      .map(t => `${formatDuration(t.seconds).padStart(8)}  ${String(t.tools).padStart(3)} tools  ${t.isAborted ? '(interrupted) ' : ''}${t.prompt || '(continuation)'}`)

    return {
      text: [
        `${list.length} turns, ${formatDuration(total)} in total, typical turn ${formatDuration(median(done.map(t => t.seconds)))}`,
        'Last 10:',
        ...lines,
      ].join('\n'),
    }
  })
}
