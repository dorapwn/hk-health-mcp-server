"""
Healthcare Snapshot Tool - Returns a one-shot view of Hong Kong's
public-hospital system across three Hospital Authority open-data
endpoints in a single MCP call.

The Hospital Authority exposes three distinct real-time datasets
relevant to a patient choosing where to seek care:

- Accident & Emergency (A&E) department waiting times, by hospital.
  Hitting A&E is the highest-cost option (long waits, no choice of
  doctor) but always available.
- General outpatient clinic quotas (4-week rolling average), by
  district. The primary-care alternative; capacity is finite and
  district-dependent.
- Specialist outpatient clinic waiting times, by specialty and
  cluster. The elective-care option; longest waits, scheduled.

A patient asking "where should I go today?" today has to call three
`tools/call` round-trips and stitch the responses together. This
module adds a single `get_healthcare_snapshot` tool that fetches
all three concurrently via `asyncio.gather` and assembles them
into one dict, with per-section failure isolation mirroring
`economy_snapshot` and `weather_summary`.

Capabilities deliberately NOT included and why:
- No filtering by hospital, district, specialty, or cluster: each
  underlying tool already exposes its own filters. The aggregator
  returns the broadest view; consumers can drill down with the
  per-section tools.
- No trend / historical analysis: all three endpoints are
  point-in-time. Use the underlying tools for time-series if HA
  starts publishing history.
"""

import asyncio
from datetime import date
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastmcp import FastMCP

from . import aed_waiting, pas_gopc_avg_quota, specialist_waiting_time_by_cluster


# Type aliases for clarity
SyncFactory = Callable[[], Any]


def _build_factories() -> List[Tuple[str, SyncFactory]]:
    """
    Return the ordered list of (section_key, callable-returning-section-data).

    Each callable returns either:
      - the underlying tool's dict (with 'data', 'last_updated', etc.),
        or
      - a dict containing 'error' if the underlying fetch already
        produced one, or
      - a list (rare; pas_gopc_avg_quota filters to a list when a
        district filter is given).

    Sections are point-in-time, so no `latest_or_none` selector is
    needed -- the underlying tool returns the current snapshot.
    """

    def _wrap(fn, *args, **kw):
        result = fn(*args, **kw)
        return result

    return [
        ("aed_waiting", lambda: _wrap(aed_waiting._get_aed_waiting_times, lang="en")),
        (
            "pas_gopc_avg_quota",
            lambda: _wrap(pas_gopc_avg_quota._get_pas_gopc_avg_quota, lang="en"),
        ),
        (
            "specialist_waiting_time_by_cluster",
            lambda: _wrap(
                specialist_waiting_time_by_cluster._get_specialist_waiting_times,
                lang="en",
            ),
        ),
    ]


async def _run_section(
    name: str, factory: SyncFactory
) -> Tuple[str, Any]:
    """Run one sync section helper in the default executor, catching all errors."""
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, factory)
        return name, result
    except Exception as exc:  # noqa: BLE001 - deliberately swallow per-section failures
        return name, {"error": f"{type(exc).__name__}: {exc}"}


async def _aggregate() -> Dict[str, Any]:
    """Fan out to all section factories concurrently and assemble the dashboard."""
    sections = _build_factories()
    tasks: List[Awaitable[Tuple[str, Any]]] = [
        _run_section(name, factory) for name, factory in sections
    ]
    results = await asyncio.gather(*tasks)
    payload: Dict[str, Any] = dict(results)
    payload["_meta"] = {
        "generated_at": date.today().isoformat(),
        "sections": [name for name, _ in sections],
        "sources": "Hospital Authority open data (HA OPDC, GOPC, SOP)",
    }
    return payload


def register(mcp: FastMCP) -> None:
    """Register the healthcare snapshot tool with the FastMCP server."""

    @mcp.tool(
        description=(
            "Get a one-shot snapshot of Hong Kong's public-hospital system: "
            "current A&E waiting times by hospital, general outpatient clinic "
            "quotas (4-week average) by district, and specialist outpatient "
            "waiting times by cluster. Internally fans out to all three "
            "Hospital Authority open-data endpoints concurrently; per-section "
            "failures are reported as {\"error\": \"...\"} rather than failing "
            "the whole call. Use this for an at-a-glance view across care "
            "options. For hospital- or specialty-specific drill-downs, call "
            "the underlying per-section tools."
        ),
    )
    async def get_healthcare_snapshot(lang: str = "en") -> Dict[str, Any]:
        """
        Aggregated Hong Kong healthcare snapshot (current state per section).

        Args:
            lang: Reserved for future use. The three underlying endpoints
                accept en/tc/sc, but the aggregator always uses en to keep
                the section keys stable across languages. Call the
                per-section tools directly if you need a different language.

        Returns:
            Dict with one key per section (aed_waiting,
            pas_gopc_avg_quota, specialist_waiting_time_by_cluster) plus a
            `_meta` key listing the sections fetched and the response
            generation date. Each section value is the underlying tool's
            response dict (with 'data', 'last_updated', etc.), or
            {\"error\": \"...\"} if that section's upstream call failed.
        """
        return await _aggregate()
