# Onedata MCP Server

An [MCP](https://modelcontextprotocol.io/) server that connects assistants to [Onedata](https://onedata.org/) (Onezone + Oneprovider): spaces, harvesters, and file operations.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) (recommended)

## Install

```bash
uv sync
```

## Environment variables

Configuration is loaded from the process environment. [python-dotenv](https://pypi.org/project/python-dotenv/) is used so a `.env` file in the **current working directory** is picked up when the server starts.

1. Copy the example file and edit values:

   ```bash
   cp .env.example .env
   ```

2. Set the variables below (see `.env.example` for placeholders).

### Onedata API (required for live calls)

| Variable | Description |
| -------- | ----------- |
| `ONEDATA_ONEZONE_HOST` | Onezone base URL, e.g. `https://your-onezone.example` (no `/api/...` suffix). |
| `ONEDATA_ONEZONE_TOKEN` | Token sent as `X-Auth-Token` to Onezone. |
| `ONEDATA_ONEPROVIDER_HOST` | Oneprovider base URL, e.g. `https://your-oneprovider.example`. |
| `ONEDATA_ONEPROVIDER_TOKEN` | Token sent as `X-Auth-Token` to Oneprovider. |
| `ONEDATA_ALLOW_INSECURE_TLS` | Set to `true` only if you must use HTTPS with self-signed or otherwise unverifiable certificates (default: verify TLS). |

### Server / logging (optional)

| Variable | Description |
| -------- | ----------- |
| `FASTMCP_LOG_LEVEL` | Logging level (default: `INFO`). |
| `FASTMCP_LOG_FILE` | If set, logs are also appended to this file path. |

## Run the MCP server (stdio)

This is the usual mode for desktop clients (Cursor, Claude Desktop, etc.):

```bash
uv run onedata-mcp
```

Ensure the client runs the command from a directory where your `.env` exists, **or** export the same variables in the environment before starting the server.

### Cursor example (`mcp.json`)

Adjust the path to your checkout:

```json
{
  "mcpServers": {
    "onedata": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/onedata-mcp",
        "onedata-mcp"
      ],
      "env": {
        "ONEDATA_ONEZONE_HOST": "https://your-onezone.example",
        "ONEDATA_ONEZONE_TOKEN": "your-token",
        "ONEDATA_ONEPROVIDER_HOST": "https://your-oneprovider.example",
        "ONEDATA_ONEPROVIDER_TOKEN": "your-token"
      }
    }
  }
}
```

You can omit `env` here and rely on a `.env` file next to the project if the server process starts with that working directory.

### MCP Inspector

```bash
uv run fastmcp dev inspector onedata_mcp/main.py:mcp
```

## Development

- Format / lint: `uv run ruff format`
- Tests: `uv run pytest`

See `AGENTS.md` for repository conventions.
