# Claude Code mods

| Mod | What it does | Command |
| --- | --- | --- |
| status-band | **Combined** band above the prompt: the live turn line plus pills for the 5h and 7d limits, input, output, cache and cost. Includes everything from usage-meter and turn-timer (their warnings, `/usage`, `/turns` and settings). Built separately on the Mac; not in this folder yet. | `/band`, `/usage`, `/turns` |
| [usage-meter](usage-meter/README.md) | Context and cost in the status line, with threshold warnings. Standalone; replaced by status-band. | `/usage` |
| [turn-timer](turn-timer/README.md) | Live turn timer, slow-turn and going-in-circles warnings. Standalone; replaced by status-band. | `/turns` |
| [activity-pane](activity-pane/README.md) | Pane of files changed, files read and commands run | `/activity` |
| [task-board](task-board/README.md) | Claude's task list as a board with progress | `/tasks` |
| [agents-panel](agents-panel/README.md) | Side panel of running and completed subagents with cost, tokens, context and time | `/agent-panel` |

All of them work on macOS and Windows, in the terminal and in the VS Code extension.
They need Claude Code 2.1.288 or newer (`claude --version`; update with `claude update`).

## Which mods to load

Load **one** of these two setups. Never load status-band together with usage-meter or
turn-timer: their warnings would show twice, and only one mod can draw the band above the prompt.

| Setup | Load these |
| --- | --- |
| **Recommended (Mac today)** | status-band, activity-pane, task-board, agents-panel |
| Standalone (no status-band on this machine) | usage-meter, turn-timer, activity-pane, task-board, agents-panel |

The usage-meter and turn-timer folders can stay on disk; a mod only runs if it is listed in
`CLAUDE_CODE_PLUGIN_DIRS`.

## Install

### Windows: one command

Unzip, open PowerShell in the `claude-mods` folder (Shift + right-click the folder >
"Open PowerShell window here") and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

It copies the mods to `%USERPROFILE%\.claude\mods\`, backs up your `settings.json`, and adds
the mod folders to `CLAUDE_CODE_PLUGIN_DIRS` while keeping everything else in the file.
If a `status-band` folder is in `claude-mods` or already in `%USERPROFILE%\.claude\mods\`, the
script loads it in place of usage-meter and turn-timer and takes those two out of the list.
Add `-DryRun` to preview first. Then restart VS Code. The manual steps below do the same thing.

### 1. Copy the mod folders

Copy each mod folder you want into a `mods` folder in your Claude config directory:

- Mac: `~/.claude/mods/`
- Windows: `C:\Users\<you>\.claude\mods\`

Each mod folder should contain `.claude-plugin` and `hooks` directly inside it, for example
`~/.claude/mods/task-board/hooks/register.tsx`.

On the Mac, from the unzipped download (status-band is already in `~/.claude/mods`):

```bash
SRC="/Users/marcus/Downloads/claude-mods-2/claude-mods"
mkdir -p ~/.claude/mods
cp -R "$SRC/activity-pane" "$SRC/task-board" "$SRC/agents-panel" ~/.claude/mods/
```

### 2. List them in settings.json

Set `CLAUDE_CODE_PLUGIN_DIRS` in the `env` block of your user settings file
(`~/.claude/settings.json`, or `C:\Users\<you>\.claude\settings.json` on Windows).
List one folder per mod. **The separator differs**: `:` on Mac, `;` on Windows.

Mac, recommended setup:

```json
{
  "env": {
    "CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/mods/status-band:~/.claude/mods/activity-pane:~/.claude/mods/task-board:~/.claude/mods/agents-panel"
  }
}
```

Windows, standalone setup (backslashes doubled inside JSON):

```json
{
  "env": {
    "CLAUDE_CODE_PLUGIN_DIRS": "C:\\Users\\<you>\\.claude\\mods\\usage-meter;C:\\Users\\<you>\\.claude\\mods\\turn-timer;C:\\Users\\<you>\\.claude\\mods\\activity-pane;C:\\Users\\<you>\\.claude\\mods\\task-board;C:\\Users\\<you>\\.claude\\mods\\agents-panel"
  }
}
```

Once status-band is on Windows too, replace the usage-meter and turn-timer entries with
`C:\\Users\\<you>\\.claude\\mods\\status-band` (or rerun the installer).

If `env` already has other entries, add this line to it with a comma between entries.
Leave out any mod you do not want.

### 3. Restart Claude Code

Close and reopen VS Code (Cmd + Q on Mac) or the terminal running `claude`, and start a new session.

### 4. Check

| Command | Comes from |
| --- | --- |
| `/band`, `/usage`, `/turns` | status-band (or usage-meter and turn-timer in the standalone setup) |
| `/activity` | activity-pane |
| `/tasks` | task-board |
| `/agent-panel` | agents-panel |

If one does not respond: `claude plugin validate ~/.claude/mods/<mod>`.

## Develop

```bash
claude plugin validate claude-mods/<mod>
claude plugin test claude-mods/<mod>
```
