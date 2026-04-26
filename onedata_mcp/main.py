import logging
import os
import sys

from fastmcp import FastMCP

from onedata_mcp.modules import files, spaces


def _setup_logging() -> logging.Logger:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    return logging.getLogger("onedata-mcp-server")


def _create_onedata_mcp_server() -> FastMCP:
    mcp = FastMCP(
        name="Onedata MCP Server",
        instructions="""
    This is an MCP server for Onedata.

    Onedata is a distributed data management system for storing, sharing, and
    collaborating on data across providers and spaces.

    Core entities:
    - Spaces: top-level shared workspaces grouping files, users, and providers.
    - Providers: services that store data and expose Oneprovider APIs.
    - Files/directories: data objects addressable by file id
      or logical path (<space_name>/<path_to_file>).
    """,
    )

    files.register_module(mcp)
    spaces.register_module(mcp)

    return mcp


def main() -> None:
    try:
        logger = _setup_logging()
        mcp.run()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")  # type: ignore
        sys.exit(0)
    except Exception as e:
        logger.error(e)  # type: ignore
        sys.exit(1)


mcp = _create_onedata_mcp_server()


if __name__ == "__main__":
    main()
