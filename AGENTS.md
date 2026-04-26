# AGENTS.md

## Setup commands
- Install deps: `uv sync`
- Start MCP server: `uv run onedata-mcp`
- Lint code: `uv run ruff format`
- Run tests: `uv run pytest`


## General Guidance
- When implementing a new MCP tool keep the interface in `onedata_mcp/modules` directory and implementation in `onedata_mcp/api`
- Always lint code and run tests after making any changes. All tests must pass.
- Add new tests for any new feature or a bug fix.