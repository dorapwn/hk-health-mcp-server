"""
Unit tests for the healthcare snapshot tool.

Same conventions as test_economy_snapshot.py:
unittest.TestCase, @patch the underlying per-section helpers
(not the HTTP layer), and assert on the consolidated structure
returned by get_healthcare_snapshot.
"""

import asyncio
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from hkopenai.hk_health_mcp_server.tools.healthcare_snapshot import (
    _aggregate,
    register,
)


class TestHealthcareSnapshotTool(unittest.TestCase):
    """Test case class for the healthcare snapshot tool."""

    def test_register_tool(self):
        """Tests that the aggregator tool is correctly registered on a FastMCP mock."""
        mock_mcp = MagicMock()
        register(mock_mcp)
        self.assertEqual(mock_mcp.tool.call_count, 1)
        decorated_func = mock_mcp.tool.return_value.call_args[0][0]
        self.assertEqual(decorated_func.__name__, "get_healthcare_snapshot")

    def test_aggregate_returns_all_three_sections(self):
        """All three sections present in the response, each populated."""
        def ok_aed(lang="en"):
            return {
                "data": {"waitTime": [{"hospName": "QEH", "topWait": "Over 2 hours"}]},
                "last_updated": "2026-10-02T10:00:00",
            }

        def ok_gopc(lang="en", district=""):
            return {
                "data": [{"District": "Tuen Mun", "AverageQuota": 50.0}],
                "last_updated": "2026-10-02T10:00:00",
                "message": "Retrieved data for 18 clinics",
            }

        def ok_sop(lang="en"):
            return {
                "data": [{"Cluster": "NTW", "Specialty": "Medicine", "WaitDays": 28}],
                "last_updated": "2026-10-02T10:00:00",
            }

        with patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.aed_waiting._get_aed_waiting_times",
            side_effect=ok_aed,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.pas_gopc_avg_quota._get_pas_gopc_avg_quota",
            side_effect=ok_gopc,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.specialist_waiting_time_by_cluster._get_specialist_waiting_times",
            side_effect=ok_sop,
        ):
            result = asyncio.run(_aggregate())

        self.assertIn("aed_waiting", result)
        self.assertIn("pas_gopc_avg_quota", result)
        self.assertIn("specialist_waiting_time_by_cluster", result)
        self.assertEqual(result["aed_waiting"]["data"]["waitTime"][0]["hospName"], "QEH")
        self.assertEqual(result["pas_gopc_avg_quota"]["data"][0]["District"], "Tuen Mun")
        self.assertEqual(
            result["specialist_waiting_time_by_cluster"]["data"][0]["WaitDays"], 28
        )

    def test_aggregate_partial_failure_isolation(self):
        """One section raising should not break the others; error captured per-section."""
        def ok_aed(lang="en"):
            return {"data": {"waitTime": []}, "last_updated": "2026-10-02T10:00:00"}

        def boom_gopc(lang="en", district=""):
            raise RuntimeError("HA GOPC endpoint returned 503")

        def ok_sop(lang="en"):
            return {"data": [], "last_updated": "2026-10-02T10:00:00"}

        with patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.aed_waiting._get_aed_waiting_times",
            side_effect=ok_aed,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.pas_gopc_avg_quota._get_pas_gopc_avg_quota",
            side_effect=boom_gopc,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.specialist_waiting_time_by_cluster._get_specialist_waiting_times",
            side_effect=ok_sop,
        ):
            result = asyncio.run(_aggregate())

        self.assertIn("aed_waiting", result)
        self.assertIn("specialist_waiting_time_by_cluster", result)
        self.assertIn("error", result["pas_gopc_avg_quota"])
        self.assertIn("503", result["pas_gopc_avg_quota"]["error"])
        # Other sections still return their actual data, not error stubs.
        self.assertEqual(result["aed_waiting"]["data"]["waitTime"], [])
        self.assertEqual(result["specialist_waiting_time_by_cluster"]["data"], [])

    def test_aggregate_includes_meta_block(self):
        """_meta block lists sections, generation date, and sources."""
        def stub_section(*args, **kwargs):
            return {"data": {}, "last_updated": "2026-10-02T10:00:00"}

        with patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.aed_waiting._get_aed_waiting_times",
            side_effect=stub_section,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.pas_gopc_avg_quota._get_pas_gopc_avg_quota",
            side_effect=stub_section,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.specialist_waiting_time_by_cluster._get_specialist_waiting_times",
            side_effect=stub_section,
        ):
            result = asyncio.run(_aggregate())

        meta = result["_meta"]
        self.assertEqual(meta["generated_at"], date.today().isoformat())
        self.assertEqual(
            set(meta["sections"]),
            {"aed_waiting", "pas_gopc_avg_quota", "specialist_waiting_time_by_cluster"},
        )
        self.assertIn("Hospital Authority", meta["sources"])

    def test_aggregate_handles_section_returning_error_dict(self):
        """If a section already returns {'error': ...}, pass it through, don't crash."""
        def ok_aed(lang="en"):
            return {"data": {"waitTime": []}, "last_updated": "2026-10-02T10:00:00"}

        def gopc_with_error(lang="en", district=""):
            return {"type": "Error", "error": "fetch_json_data returned 502"}

        def ok_sop(lang="en"):
            return {"data": [], "last_updated": "2026-10-02T10:00:00"}

        with patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.aed_waiting._get_aed_waiting_times",
            side_effect=ok_aed,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.pas_gopc_avg_quota._get_pas_gopc_avg_quota",
            side_effect=gopc_with_error,
        ), patch(
            "hkopenai.hk_health_mcp_server.tools.healthcare_snapshot.specialist_waiting_time_by_cluster._get_specialist_waiting_times",
            side_effect=ok_sop,
        ):
            result = asyncio.run(_aggregate())

        # The pas_gopc section's error dict is passed through verbatim.
        self.assertEqual(
            result["pas_gopc_avg_quota"],
            {"type": "Error", "error": "fetch_json_data returned 502"},
        )


if __name__ == "__main__":
    unittest.main()
