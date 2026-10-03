import { atom, read, update } from 'claude-code'
import type { Register, SessionContextUsage, SessionCost, SessionRateLimit } from 'claude-code'

import type { CostLevel } from '../types'

const isContextWarned = atom({ plugin: 'usage-meter', key: 'isContextWarned' } as const, false)
const costLevel = atom({ plugin: 'usage-meter', key: 'costLevel' } as const, 0)

const WARN_MS = 10000

export const formatTokens = (n: number): string =>
  n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`

export const formatUsd = (usd: number): string => `$${usd.toFixed(2)}`

export const statusLine = (context: SessionContextUsage, cost?: SessionCost): string => {
  const ctx =
    context.tokens === undefined
      ? `Context -/${formatTokens(context.window)}`
      : `Context ${formatTokens(context.tokens)}/${formatTokens(context.window)} (${context.percent ?? 0}%)`

  return cost ? `${ctx} | ${formatUsd(cost.usd)} this session` : ctx
}

// 0 below the first threshold, 1 past it, 2 past it plus one step, and so on.
export const levelFor = (usd: number, first: number, step: number): CostLevel =>
  usd < first ? 0 : 1 + Math.floor((usd - first) / Math.max(step, 0.01))

const rateLine = (limit: SessionRateLimit): string =>
  `${limit.kind}: ${Math.round(limit.percentUsed)}% used${limit.resetsAt ? `, resets ${limit.resetsAt}` : ''}`

export const register: Register = (on, options) => {
  const contextWarnTokens = Number(options.contextWarnTokens ?? 300000)
  const costWarnUsd = Number(options.costWarnUsd ?? 50)
  const costStepUsd = Number(options.costStepUsd ?? 50)

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    await $.command.register({
      name: 'usage',
      description: 'Show context used, session cost and rate limits',
    })
    const { context, cost } = await $.session.usage()
    $.ui.status(statusLine(context, cost))

    return ran
  })

  on('session.measure', async ($, e, next) => {
    $.ui.status(statusLine(e.context, e.cost))

    const tokens = e.context.tokens
    if (tokens !== undefined) {
      const isOver = tokens >= contextWarnTokens
      const wasWarned = await read($, isContextWarned)
      if (isOver && !wasWarned) {
        $.ui.toast(
          `Context is at ${formatTokens(tokens)} tokens. Consider /compact or starting a fresh session.`,
          { timeoutMs: WARN_MS },
        )
      }
      // Re-arms after /compact brings the window back under the threshold.
      if (isOver !== wasWarned) await update($, isContextWarned, () => isOver)
    }

    if (e.cost) {
      const level = levelFor(e.cost.usd, costWarnUsd, costStepUsd)
      if (level > (await read($, costLevel))) {
        $.ui.toast(`This session has cost ${formatUsd(e.cost.usd)} so far.`, { timeoutMs: WARN_MS })
        await update($, costLevel, () => level)
      }
    }

    return next(e)
  })

  on('command.run', { command: 'usage' }, async $ => {
    const { context, cost, rateLimits } = await $.session.usage()
    const lines = [
      statusLine(context, cost),
      `Warnings: context at ${formatTokens(contextWarnTokens)} tokens, cost at ${formatUsd(costWarnUsd)} then every ${formatUsd(costStepUsd)}`,
      ...rateLimits.map(rateLine),
    ]

    return { text: lines.join('\n') }
  })
}
