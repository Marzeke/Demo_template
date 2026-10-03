# Claude Code mods

| Mod | What it does | Command |
| --- | --- | --- |
| [usage-meter](usage-meter/README.md) | Context and cost in the status line, with threshold warnings | `/usage` |
| [activity-pane](activity-pane/README.md) | Pane of files changed, files read and commands run | `/activity` |
| [turn-timer](turn-timer/README.md) | Live turn timer, slow-turn and going-in-circles warnings | `/turns` |
| [task-board](task-board/README.md) | Claude's task list as a board with progress | `/tasks` |

All four work on macOS and Windows, in the terminal and in the VS Code extension.
They need Claude Code 2.1.288 or newer (`claude --version`; update with `claude update`).

## Install

### 1. Copy the mod folders

Copy each mod folder you want into a `mods` folder in your Claude config directory:

- Mac: `~/.claude/mods/`
- Windows: `C:\Users\<you>\.claude\mods\`

Each mod folder should contain `.claude-plugin` and `hooks` directly inside it, for example
`~/.claude/mods/turn-timer/hooks/register.ts`.

### 2. List them in settings.json

Add `CLAUDE_CODE_PLUGIN_DIRS` to the `env` block of your user settings file
(`~/.claude/settings.json`, or `C:\Users\<you>\.claude\settings.json` on Windows).
List one folder per mod. **The separator differs**: `:` on Mac, `;` on Windows.

Mac:

```json
{
  "env": {
    "CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/mods/usage-meter:~/.claude/mods/activity-pane:~/.claude/mods/turn-timer:~/.claude/mods/task-board"
  }
}
```

Windows (backslashes doubled inside JSON):

```json
{
  "env": {
    "CLAUDE_CODE_PLUGIN_DIRS": "C:\\Users\\<you>\\.claude\\mods\\usage-meter;C:\\Users\\<you>\\.claude\\mods\\activity-pane;C:\\Users\\<you>\\.claude\\mods\\turn-timer;C:\\Users\\<you>\\.claude\\mods\\task-board"
  }
}
```

If `env` already has other entries, add this line to it with a comma between entries.
Leave out any mod you do not want.

### 3. Restart Claude Code

Close and reopen VS Code (or the terminal running `claude`) and start a new session.

## Develop

```bash
claude plugin validate claude-mods/<mod>
claude plugin test claude-mods/<mod>
```
