# task-board

Shows Claude's task list as a board while it works through multi-step jobs.

- **Pane** with a progress bar and every task: `[x]` done, `[>]` in progress (highlighted, with
  what Claude is doing right now), `[ ]` still to do.
- **Status line**: `Tasks 3/7 | Running tests`, so you can follow along even with the pane closed.
- **`/tasks`**: opens the board.

The board opens by itself the first time Claude creates a task in a session (on terminals
about 144 columns or wider; otherwise use `/tasks`). Turn that off in `/config`
("Open when Claude starts a task list").

It follows both of Claude Code's task tools (the task list and the older to-do list).

Install: see [../README.md](../README.md).
