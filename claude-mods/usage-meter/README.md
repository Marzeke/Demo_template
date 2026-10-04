# usage-meter

> **Replaced by status-band** where status-band is installed (it includes everything here).
> Load this mod only on a machine without status-band, and never alongside it.

A Claude Code mod that keeps an eye on how big and how expensive a session is getting.

- **Status line** under the prompt, always visible:
  `Context 312k/1M (31%) | $12.40 this session`
- **Context warning**: a pop-up once the context passes 300k tokens, suggesting `/compact`
  or a fresh session. After you compact and it drops back under, it re-arms.
- **Cost warning**: a pop-up when the session first passes $50, then again every further $50.
- **`/usage`**: prints the figures above plus your rate-limit windows.

It uses only Claude Code's own APIs (no shell commands or file access), so the same files
work unchanged on macOS and Windows, in the terminal and in the VS Code extension.

Requires Claude Code 2.1.288 or newer (`claude --version`; update with `claude update`).

## Install

### 1. Copy the folder

Copy this `usage-meter` folder (the one containing `.claude-plugin`, `hooks` and `types`)
into a `mods` folder under your Claude config directory:

| Machine | Destination |
| --- | --- |
| Mac | `~/.claude/mods/usage-meter` |
| Windows | `C:\Users\<you>\.claude\mods\usage-meter` |

From a clone of this repo:

```bash
# Mac (Terminal)
mkdir -p ~/.claude/mods && cp -R claude-mods/usage-meter ~/.claude/mods/
```

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\mods" | Out-Null
Copy-Item -Recurse -Force claude-mods\usage-meter "$env:USERPROFILE\.claude\mods\"
```

Note: `.claude-plugin` starts with a dot, so Finder hides it by default. Copying the
whole `usage-meter` folder brings it along.

### 2. Load it in every session

Add the folder to the `env` block of your user settings file, `~/.claude/settings.json`
(Windows: `C:\Users\<you>\.claude\settings.json`). If the file already has an `env`
block, add the line to it rather than creating a second one.

Mac:

```json
{
  "env": {
    "CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/mods/usage-meter"
  }
}
```

Windows (backslashes doubled inside JSON):

```json
{
  "env": {
    "CLAUDE_CODE_PLUGIN_DIRS": "C:\\Users\\<you>\\.claude\\mods\\usage-meter"
  }
}
```

This works for the terminal and for the VS Code extension. To try it for a single
session first, run `claude --plugin-dir ~/.claude/mods/usage-meter` instead.

To load more mods later, list several folders separated by `:` on Mac or `;` on Windows.

### 3. Check it

Start a new session, send one message, and the status line appears under the prompt.
Type `/usage` to see the full figures.

## Change the thresholds

Run `/config` in Claude Code; the mod adds three rows:

| Setting | Default |
| --- | --- |
| Context warning (tokens) | 300000 |
| First cost warning (USD) | 50 |
| Repeat cost warning every (USD) | 50 |

Or set them in `settings.json`:

```json
{
  "pluginConfigs": {
    "usage-meter": {
      "options": { "contextWarnTokens": 200000, "costWarnUsd": 25, "costStepUsd": 25 }
    }
  }
}
```

## Notes

- Cost is the session's total as `/cost` reports it. On a subscription plan this is
  an estimate of API-equivalent spend, not what you are billed.
- Context figures appear after the first reply of a session (or after a compact).

## Develop

```bash
claude plugin validate claude-mods/usage-meter
claude plugin test claude-mods/usage-meter
```
