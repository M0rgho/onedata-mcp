import logging
import os
import sys

from fastmcp import FastMCP

from onedata_mcp.modules import files, harvesters, spaces
from onedata_mcp.token_policy import resolve_register_write_tools_sync


def _setup_logging() -> logging.Logger:
    """Configure logging for the server."""
    log_level = os.environ.get("FASTMCP_LOG_LEVEL", "INFO")
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file = os.environ.get("FASTMCP_LOG_FILE")

    logging.basicConfig(level=log_level, format=log_format, force=True)

    print(f"Log file: {log_file}, log level: {log_level}")
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
            logging.info("Logging to file: %s", log_file)
        except Exception as e:
            logging.error("Failed to set up log file %s: %s", log_file, e)

    return logging.getLogger("onedata-mcp-server")


ONEDATA_MCP_SERVER_INSTRUCTIONS = """
This is an MCP server for Onedata. Available tools depend on token permissions: if the token has the
`data.readonly` caveat, only read-only tools are available.

Onedata stores data in spaces. Files are addressed by logical path `/<space_name>/<path_to_file>`
or by file id. All absolute path arguments must start with '/'. Relative paths are not supported.
Tools accepting file_id_or_path - can be called with either the absolute logical path or the id.
Id does not start with '/'.


How to work efficiently:
  - When the user names a file (basename or full path), open it with `get_file_metadata` or
    `get_file_attributes` on the logical path. Do not walk `list_files` pages (token/offset) to
    hunt for one filename in a large directory.

  - When you only know a filename and not the path, resolve it with the space harvester index
    or `list_files_recursive` with a matching `prefix`. Do not scan thousands of entries via
    repeated `list_files`.
  
  - Use `list_files` only to explore an unknown directory structure, not to find a known file.

Harvester indexes (Elasticsearch-style) hold searchable document fields plus `__onedata.*` file
fields. Before searching, call `get_harvester_index_schema` with the harvester and index id.
The response includes a configured `schema` JSON string — read `mappings.properties` for
top-level field names and nested object shapes. Prefer those declared paths when building
`term` / `bool` filters.

""".strip()


def _create_onedata_mcp_server() -> FastMCP:
    mcp = FastMCP(
        name="Onedata MCP Server",
        instructions=ONEDATA_MCP_SERVER_INSTRUCTIONS,
    )

    register_writers = resolve_register_write_tools_sync()
    files.register_module(mcp, register_writers=register_writers)
    harvesters.register_module(mcp)
    spaces.register_module(mcp)

    return mcp


logger = _setup_logging()
mcp = _create_onedata_mcp_server()


def main() -> None:
    """Main entry point for the Onedata MCP Server."""
    try:
        logger.info("Server started")
        mcp.run()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")  # type: ignore
        sys.exit(0)
    except Exception as e:
        logger.error(e)  # type: ignore
        sys.exit(1)


if __name__ == "__main__":
    main()
