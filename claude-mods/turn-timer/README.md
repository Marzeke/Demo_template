# turn-timer

> **Replaced by status-band** where status-band is installed (it includes everything here).
> Load this mod only on a machine without status-band, and never alongside it.

Times every turn and flags the ones that look wrong.

- **While Claude works**, the status line shows a live timer: `Working 1m 20s | 12 tool calls`.
- **When the turn ends**: `Last turn 2m 05s | 18 tool calls`.
- **Slow turn pop-up** when a turn takes longer than 5 minutes, or (once there are a few turns
  to compare with) more than 4 times your usual turn length and over a minute.
- **Going-in-circles pop-up** when Claude makes the identical tool call 3 times in one turn
  (for example running the same failing command again and again).
- **`/turns`**: the last 10 turns with duration, tool calls and the prompt that started each,
  plus the session total and typical turn length.

Settings in `/config`: "Slow turn warning (seconds)" (default 300) and
"Repeated command warning (times)" (default 3).

Install: see [../README.md](../README.md).
