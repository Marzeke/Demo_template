# Claude Code mods: what is installed where

The record of which mods each machine runs, how it was set up, and what is still to do.
Update this file whenever a machine's setup changes.

Last updated: 2026-10-04

## Machines

| | Mac (MacBook Air) | Windows home PC | Windows work laptop (Schenker) |
| --- | --- | --- | --- |
| User folder | `/Users/marcus` | `C:\Users\marcu` | `C:\Users\MZIYEUNG` |
| Claude config | `~/.claude` | `C:\Users\marcu\.claude` | `C:\Users\MZIYEUNG\.claude` |
| Mods folder | `~/.claude/mods` | `C:\Users\marcu\.claude\mods` | `C:\Users\MZIYEUNG\.claude\mods` |
| Setup | **Recommended**: status-band, activity-pane, task-board, agents-panel | **Standalone**: usage-meter, turn-timer, activity-pane, task-board, agents-panel | **Standalone** (same as home PC) |
| How to install | Manual copy (Mac steps below) | `install-windows.ps1` | `install-windows.ps1`; if scripts are blocked, manual steps |
| status-band | Built locally on this Mac (not in the repo) | Not available until copied into the repo | Not available until copied into the repo |
| State | Installed. Copy the new agents-panel 0.3.0 (detailed pixel mascots) | Instructions given. Check the settings line uses `marcu`, not `MZIYEUNG` | Not installed yet |

Notes:
- The Mac's `~/.claude/mods` holds activity-pane, agents-panel, status-band, task-board and an
  old `usage-meter` folder (checked 2026-10-04; `turn-timer` is gone). usage-meter stays on disk
  but is **not** in the settings line, so it does not load. That is intended.
- The work laptop is a managed Schenker machine: PowerShell scripts may be blocked by policy.
  Use the manual Windows steps there if the installer will not run.
- The two Windows PCs have **different user folders** (`marcu` vs `MZIYEUNG`). The installer
  works this out itself; hand-written paths must match the machine.

## The mods

| Mod | Command(s) | Notes |
| --- | --- | --- |
| status-band | `/band`, `/usage`, `/turns` | Combines usage-meter + turn-timer into a band above the prompt (turn line, 5h/7d limit pills, input/output/cache/cost). Only one mod can draw above the prompt. |
| usage-meter | `/usage` | Standalone. Replaced by status-band. |
| turn-timer | `/turns` | Standalone. Replaced by status-band. |
| activity-pane | `/activity` | Pane: files changed, files read, commands run. |
| task-board | `/tasks` | Pane: Claude's task list with progress. |
| agents-panel | `/agent-panel` | Side panel of subagents with mascots, model, effort tier, context, tokens, cost, time. Not `/agents` (built-in). |

Rules:
- Agents-panel mascots use the **screenshot** colours (the default) on every machine. Leave
  "Mascot colours" in `/config` on `screenshot`.
- Load status-band **or** usage-meter + turn-timer, never both.
- Mods only run when listed in `CLAUDE_CODE_PLUGIN_DIRS` in the user `settings.json`.
- Separator: `:` on Mac, `;` on Windows. Windows paths need doubled backslashes in JSON.
- After any change: fully quit VS Code (Cmd + Q on Mac) and reopen, or start a new `claude`.
- All mods need Claude Code 2.1.288 or newer (`claude --version`, `claude update`).

## Getting the latest files

The mods live in the `claude-mods/` folder of `Marzeke/Demo_template`, branch
`ccr-3e6648f1-aqoyah` (not yet merged to `main`). Download that folder (or the
`claude-mods.zip` from the Claude session), then follow the steps for the machine.

## Mac: update or reinstall

```bash
SRC="/Users/marcus/Downloads/claude-mods-2/claude-mods"   # wherever the new download was unzipped
mkdir -p ~/.claude/mods
cp -R "$SRC/activity-pane" "$SRC/task-board" "$SRC/agents-panel" ~/.claude/mods/
ls ~/.claude/mods/*/.claude-plugin/plugin.json
```

The settings line in `~/.claude/settings.json` (inside `"env"`) must be exactly:

```json
"CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/mods/status-band:~/.claude/mods/activity-pane:~/.claude/mods/task-board:~/.claude/mods/agents-panel"
```

Do not copy usage-meter or turn-timer again, and do not overwrite status-band from a download
(it is the locally built version).

## Windows home PC (marcu): update or reinstall

In the unzipped `claude-mods` folder, Shift + right-click > "Open PowerShell window here":

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -DryRun   # preview
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

It copies the mods, backs up `settings.json`, and sets the settings line. If a `status-band`
folder is present it uses that instead of usage-meter and turn-timer. Expected line today:

```json
"CLAUDE_CODE_PLUGIN_DIRS": "C:\\Users\\marcu\\.claude\\mods\\usage-meter;C:\\Users\\marcu\\.claude\\mods\\turn-timer;C:\\Users\\marcu\\.claude\\mods\\activity-pane;C:\\Users\\marcu\\.claude\\mods\\task-board;C:\\Users\\marcu\\.claude\\mods\\agents-panel"
```

## Windows work laptop (MZIYEUNG): install

Try the installer as above. If PowerShell refuses to run it:

1. Copy the five mod folders into `C:\Users\MZIYEUNG\.claude\mods\`.
2. Open `notepad %USERPROFILE%\.claude\settings.json` and set, inside `"env"`:

```json
"CLAUDE_CODE_PLUGIN_DIRS": "C:\\Users\\MZIYEUNG\\.claude\\mods\\usage-meter;C:\\Users\\MZIYEUNG\\.claude\\mods\\turn-timer;C:\\Users\\MZIYEUNG\\.claude\\mods\\activity-pane;C:\\Users\\MZIYEUNG\\.claude\\mods\\task-board;C:\\Users\\MZIYEUNG\\.claude\\mods\\agents-panel"
```

3. Save (type "All Files" so it does not become `settings.json.txt`), restart VS Code.

## Moving to status-band on Windows (later)

1. On the Mac, ask Claude Code to copy `~/.claude/mods/status-band` into `claude-mods/` in
   this repo and push it to the same branch.
2. On each Windows PC, download the new `claude-mods` and rerun `install-windows.ps1`.
   It switches the settings line to status-band and drops usage-meter and turn-timer.
3. Update the table at the top of this file.

## Change log

| Date | Change |
| --- | --- |
| 2026-10-03 | usage-meter built (status line for context and cost, warnings, `/usage`). |
| 2026-10-03 | activity-pane, turn-timer and task-board built. Windows installer added. |
| 2026-10-03 | Windows paths corrected: home PC user is `marcu`, work laptop is `MZIYEUNG`. |
| 2026-10-04 | agents-panel built (side panel of subagents). |
| 2026-10-04 | Mac: status-band (built locally) replaces usage-meter and turn-timer. Installer and README updated to match. |
| 2026-10-04 | agents-panel: mascots added (hat shape per effort tier, legs walk while running). |
| 2026-10-04 | agents-panel 0.2.0: pixel-art mascots like the reference screenshot; colour themes `screenshot` (default), `claude`, `simple` in `/config`. Copy the new agents-panel folder to each machine. |
| 2026-10-04 | Mac mods folder checked: activity-pane, agents-panel, status-band, task-board, usage-meter (unloaded). Settings line confirmed as status-band, activity-pane, task-board, agents-panel. |
| 2026-10-04 | Decision: mascots stay on the screenshot colours on all machines. |
| 2026-10-04 | agents-panel 0.3.0: more detailed 16x16 mascots in Claude Code's mascot shape (arms, four legs), speckled beanie with flag, hard hat with badge, ridged helmet with goggles band and visor, cap with chequered flag, twinkle sparkle. |
