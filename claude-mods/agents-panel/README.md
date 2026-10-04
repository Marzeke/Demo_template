# agents-panel

A side panel showing every subagent Claude starts in a session.

- **Totals** across all agents: cost, tokens and elapsed time.
- **A pixel-art mascot per agent**: its hat shows the effort tier (beanie and flag = heavy,
  hard hat = careful, cap and goggles = medium, green cap and chequered flag = light). Its legs
  walk while it runs, a sparkle appears when it finishes, and it fades if stopped or failed.
  Drawn as a pixel grid in the terminal and as a vector image in VS Code and the desktop app.
- **Running** agents, each with its task, a tier word from its effort (light, medium,
  careful, heavy), model and effort, context used (% and tokens), cost so far and a live
  clock, plus a context bar.
- **Completed** agents (click to collapse), marked done, FAILED or stopped.
- **`/agent-panel`**: opens the panel.

It opens by itself the first time an agent starts in a session (on terminals about 144
columns or wider; otherwise use `/agent-panel`). Turn that off in `/config`
("Open when an agent starts").

Mascot colours, also in `/config` ("Mascot colours"):

| Option | Look |
| --- | --- |
| `screenshot` (default) | Coral critters with brown, gold, grey/blue and green hats |
| `claude` | Claude's terracotta with Claude's palette for the hats |
| `simple` | Small one-colour text critters |


Notes:
- Per-agent cost is an estimate (shown with ≈): the mod assigns each increase in the
  session's total cost to the agent whose request just finished, so agents running at the
  same moment can swap a little cost between them. The session total is exact.
- Context % is measured against the main session's context window.
- Agents launched by a workflow appear once they first use a tool.

Install: see [../README.md](../README.md).
