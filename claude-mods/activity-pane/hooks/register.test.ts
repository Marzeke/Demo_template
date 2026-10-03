import { expect, test } from 'claude-code/testing'
import type { RenderPropsOf } from 'claude-code'

import { relativePath, uniqueFiles } from './register'

const PANE_PROPS = {
  title: 'Activity', isFocused: false, bodyColumns: 60, placement: 'dock',
  scroll: { offset: 0, bodyRows: 30 }, view: {},
} as unknown as RenderPropsOf['Pane']

test('paths are shown relative to the project on Mac and Windows', () => {
  expect(relativePath('/Users/m/proj/src/a.ts', '/Users/m/proj')).toBe('src/a.ts')
  expect(relativePath('C:\\Users\\M\\proj\\src\\a.bas', 'C:\\Users\\M\\proj')).toBe('src/a.bas')
  expect(relativePath('c:\\users\\m\\PROJ\\b.bas', 'C:\\Users\\M\\proj')).toBe('b.bas')
  expect(relativePath('/etc/hosts', '/Users/m/proj')).toBe('/etc/hosts')
})

test('unique files are most recent first with counts', () => {
  const e = (id: string, label: string) => ({ id, kind: 'changed' as const, label, tool: 'Edit', state: 'ok' as const })
  expect(uniqueFiles([e('1', 'a'), e('2', 'b'), e('3', 'a')], 'changed')).toEqual([
    { label: 'a', count: 2 },
    { label: 'b', count: 1 },
  ])
})

test('pane lists changed files, read files and failed commands', async ($, on) => {
  on('tool.call', (_, e) =>
    String(e.tool) === 'Bash' && JSON.stringify(e).includes('false')
      ? { result: { stdout: '', stderr: 'boom', interrupted: false }, isError: true }
      : { result: {} as never },
  )

  await $.tool.call({ tool: 'Read', file_path: '/p/readme.md' })
  await $.tool.call({ tool: 'Edit', file_path: '/p/src/x.ts', old_string: 'a', new_string: 'b' })
  await $.tool.call({ tool: 'Bash', command: 'false' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'activity-pane', surface, component: 'Pane', requestId: 'activity', props: PANE_PROPS })
    expect(await ui.find({ text: /Changed \(1\)/ })).toBeDefined()
    expect(await ui.find({ text: /\/p\/src\/x\.ts/ })).toBeDefined()
    expect(await ui.find({ text: /Read \(1\)/ })).toBeDefined()
    expect(await ui.find({ text: /Commands \(1, 1 failed\)/ })).toBeDefined()

    await ui.press({ key: 'timeline' })
    expect(await ui.find({ text: /run\s+false/ })).toBeDefined()
    await ui.press({ key: 'files' })
    await ui.unmount()
  }
})
