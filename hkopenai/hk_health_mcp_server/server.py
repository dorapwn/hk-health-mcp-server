"""
Module for creating and running the HK OpenAI Health MCP Server.
This server provides tools for accessing health-related data in Hong Kong.
"""

from fastmcp import FastMCP
from .tools import aed_waiting, specialist_waiting_time_by_cluster, pas_gopc_avg_quota, healthcare_snapshot


def server():
    """
    Create and configure the MCP server for HK OpenAI Health services.
    This function initializes the server with necessary tools for health data access.

    Returns:
        FastMCP: Configured MCP server instance with health tools registered.
    """
    mcp = FastMCP(name="HK OpenAI Health Server")

    aed_waiting.register(mcp)
    specialist_waiting_time_by_cluster.register(mcp)
    pas_gopc_avg_quota.register(mcp)
    healthcare_snapshot.register(mcp)

    return mcp
