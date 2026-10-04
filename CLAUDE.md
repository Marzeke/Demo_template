# Notes for Claude

## Claude Code mods

`claude-mods/` holds Marcus's Claude Code mods (plugins of function hooks).

- `claude-mods/MACHINES.md` records which mods each machine runs (Mac, Windows home PC,
  Windows work laptop), how each was installed and what is still to do. Read it before
  giving setup or update steps, and update its table and change log after any change.
- `claude-mods/README.md` is the general install guide; each mod has its own README.
- Check a mod with `claude plugin validate claude-mods/<mod>` and `claude plugin test claude-mods/<mod>`.
- Load status-band **or** usage-meter + turn-timer, never both.
