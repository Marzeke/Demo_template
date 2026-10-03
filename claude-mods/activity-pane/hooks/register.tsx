import { atom, read, update } from 'claude-code'
import type { Register, ToolCallInput } from 'claude-code'

import type { ActivityEntry, ActivityKind, ActivityView } from '../types'

const PANE = 'activity'
const MAX_ENTRIES = 500
const ACCENT = '#4B87E0'

const entries = atom({ plugin: 'activity-pane', key: 'entries' } as const, [])
const view = atom({ plugin: 'activity-pane', key: 'view' } as const, 'files')
const cwd = atom({ plugin: 'activity-pane', key: 'cwd' } as const, '')

// Shows a path relative to the project folder, with either slash style (Mac or Windows).
export const relativePath = (path: string, root: string): string => {
  if (!root) return path
  const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '')
  const p = norm(path)
  const r = norm(root)
  const isWindows = /^[a-z]:\//i.test(r)
  const isInside = isWindows ? p.toLowerCase().startsWith(`${r.toLowerCase()}/`) : p.startsWith(`${r}/`)

  return isInside ? p.slice(r.length + 1) : path
}

const oneLine = (text: string, max = 80): string => {
  const flat = text.replace(/\s+/g, ' ').trim()

  return flat.length > max ? `${flat.slice(0, max - 3)}...` : flat
}

const str = (value: unknown): string => (typeof value === 'string' ? value : '')

export const classify = (e: ToolCallInput, root: string): { kind: ActivityKind; label: string } => {
  const args = e as unknown as Record<string, unknown>
  const tool = String(e.tool)
  switch (tool) {
    case 'Edit':
    case 'MultiEdit':
    case 'Write':
      return { kind: 'changed', label: relativePath(str(args.file_path), root) }
    case 'NotebookEdit':
      return { kind: 'changed', label: relativePath(str(args.notebook_path), root) }
    case 'Read':
      return { kind: 'read', label: relativePath(str(args.file_path), root) }
    case 'Glob':
    case 'Grep':
      return { kind: 'searched', label: oneLine(str(args.pattern)) }
    case 'Bash':
    case 'PowerShell':
      return { kind: 'command', label: oneLine(str(args.command)) }
    default:
      return { kind: 'other', label: tool }
  }
}

// Unique files of one kind, most recent first, with how many times each was touched.
export const uniqueFiles = (list: readonly ActivityEntry[], kind: ActivityKind) => {
  const counts = new Map<string, number>()
  for (const entry of list) {
    if (entry.kind === kind && entry.label) counts.set(entry.label, (counts.get(entry.label) ?? 0) + 1)
  }
  const order: string[] = []
  for (let i = list.length - 1; i >= 0; i--) {
    const entry = list[i]
    if (entry && entry.kind === kind && entry.label && !order.includes(entry.label)) order.push(entry.label)
  }

  return order.map(label => ({ label, count: counts.get(label) ?? 1 }))
}

const KIND_WORD: Record<ActivityKind, string> = {
  changed: 'edit',
  read: 'read',
  searched: 'find',
  command: 'run ',
  other: 'tool',
}

export const register: Register = (on, options) => {
  const autoOpen = options.autoOpen !== false

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    await update($, cwd, () => ran.cwd)
    await $.command.register({ name: 'activity', description: 'Show files changed, files read and commands run' })
    if (autoOpen) void $.ui.open({ id: PANE, title: 'Activity' })

    return ran
  })

  on('command.run', { command: 'activity' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Activity' })

    return { text: 'Activity pane opened.' }
  })

  on('tool.call', async ($, e, next) => {
    const { kind, label } = classify(e, await read($, cwd))
    const entry: ActivityEntry = { id: e.tool_use_id, kind, label, tool: String(e.tool), state: 'running' }
    await update($, entries, list => [...list, entry].slice(-MAX_ENTRIES))

    const ran = await next(e)
    const state = ran.deny !== undefined || ran.isError === true ? 'failed' : 'ok'
    await update($, entries, list => list.map(one => (one.id === entry.id ? { ...one, state } : one)))

    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const list = await read($, entries)
    const current = await read($, view)
    const room = Math.max(4, (e.viewport?.rows ?? 30) - 6)
    const setView = (next: ActivityView) => () => update($, view, () => next)

    const header = (
      <Box flexDirection="row" key="tabs">
        <Button key="files" label={current === 'files' ? '[Files]' : 'Files'} onPress={setView('files')} />
        <Text> </Text>
        <Button key="timeline" label={current === 'timeline' ? '[Timeline]' : 'Timeline'} onPress={setView('timeline')} />
      </Box>
    )

    if (list.length === 0) {
      return (
        <Box flexDirection="column">
          {header}
          <Text dimColor>Nothing yet. Files and commands appear here as Claude works.</Text>
        </Box>
      )
    }

    if (current === 'timeline') {
      return (
        <Box flexDirection="column">
          {header}
          {list.slice(-room).map(entry => (
            <Text key={entry.id} wrap="truncate-end" dimColor={entry.state === 'ok' && entry.kind === 'read'}>
              {entry.state === 'running' ? '..' : entry.state === 'failed' ? '!!' : '  '} {KIND_WORD[entry.kind]} {entry.label}
            </Text>
          ))}
        </Box>
      )
    }

    const changed = uniqueFiles(list, 'changed')
    const readFiles = uniqueFiles(list, 'read')
    const commands = list.filter(entry => entry.kind === 'command')
    const failed = commands.filter(entry => entry.state === 'failed').length
    const share = Math.max(2, Math.floor((room - 3) / 3))

    return (
      <Box flexDirection="column">
        {header}
        <Text bold color={ACCENT}>Changed ({changed.length})</Text>
        {changed.length === 0 && <Text dimColor>  none</Text>}
        {changed.slice(0, share).map(f => (
          <Text key={`c:${f.label}`} wrap="truncate-start">  {f.label}{f.count > 1 ? `  x${f.count}` : ''}</Text>
        ))}
        {changed.length > share && <Text dimColor>  +{changed.length - share} more</Text>}
        <Text bold color={ACCENT}>Read ({readFiles.length})</Text>
        {readFiles.slice(0, share).map(f => (
          <Text key={`r:${f.label}`} dimColor wrap="truncate-start">  {f.label}</Text>
        ))}
        {readFiles.length > share && <Text dimColor>  +{readFiles.length - share} more</Text>}
        <Text bold color={ACCENT}>
          Commands ({commands.length}{failed > 0 ? `, ${failed} failed` : ''})
        </Text>
        {commands.slice(-share).map(c => (
          <Text key={`x:${c.id}`} wrap="truncate-end" dimColor={c.state === 'ok'}>
            {c.state === 'failed' ? '!!' : c.state === 'running' ? '..' : '  '} {c.label}
          </Text>
        ))}
      </Box>
    )
  })
}
