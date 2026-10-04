# agents-panel

A side panel showing every subagent Claude starts in a session.

- **Totals** across all agents: cost, tokens and elapsed time.
- **A mascot per agent**: its hat shows the effort tier (small cap = light, flat cap = medium,
  hard hat = careful, big hat = heavy), its legs walk while it runs, and it shows `x` eyes if it failed.
- **Running** agents, each with its task, a tier word from its effort (light, medium,
  careful, heavy), model and effort, context used (% and tokens), cost so far and a live
  clock, plus a context bar.
- **Completed** agents (click to collapse), marked done, FAILED or stopped.
- **`/agent-panel`**: opens the panel.

It opens by itself the first time an agent starts in a session (on terminals about 144
columns or wider; otherwise use `/agent-panel`). Turn that off in `/config`
("Open when an agent starts").

Notes:
- Per-agent cost is an estimate (shown with ≈): the mod assigns each increase in the
  session's total cost to the agent whose request just finished, so agents running at the
  same moment can swap a little cost between them. The session total is exact.
- Context % is measured against the main session's context window.
- Agents launched by a workflow appear once they first use a tool.

Install: see [../README.md](../README.md).
