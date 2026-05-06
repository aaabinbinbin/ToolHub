# TOOLHUB.md

## Project Background

ToolHub is an Agent Harness platform for CLI and IDE agents. It manages MCP, HTTP, CLI, and Sandbox tools through a common runtime with routing, permissions, execution audit logs, and observability.

## Safety Rules

- Do not delete host files.
- Do not run destructive host commands.
- Do not start arbitrary local processes from user input.
- Prefer sandboxed execution for generated code and shell commands.
- Treat high-risk tools as requiring explicit permission unless the run mode allows them.

## Execution Preferences

- Keep tool calls auditable with task events, tool calls, LLM calls, and sandbox execution records.
- Use `PLAN_ONLY`, `SAFE_EXECUTE`, and `FULL_EXECUTE` run modes to decide how much execution is allowed.
- Prefer clear JSON-like intermediate results for intent, routing, permission, and summary nodes.
