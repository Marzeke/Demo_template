# activity-pane

A side pane listing what Claude has done this session.

- **Files tab**: files changed (with how many times each), files read, and commands run,
  with failed commands marked `!!`.
- **Timeline tab**: every tool call in order; `..` while running, `!!` if it failed.
- **`/activity`**: opens the pane.

It opens automatically when a session starts if the terminal is wide enough (about 144
columns); otherwise type `/activity`. Turn auto-open off in `/config`
("Open the pane automatically").

Paths are shown relative to the project folder, on both Mac and Windows.

Install: see [../README.md](../README.md).
