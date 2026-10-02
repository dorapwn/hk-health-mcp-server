"""
Module for testing the AED waiting times data fetching functionality.
This module contains unit tests to verify the behavior of the AED data retrieval.
"""

from datetime import datetime
import json

import unittest
from unittest.mock import patch, mock_open, MagicMock

from hkopenai.hk_health_mcp_server.tools.aed_waiting import (
    _get_aed_waiting_times,
    register,
)


class TestAEDWaitingTimes(unittest.TestCase):
    """
    Test class for verifying AED waiting times data fetching.
    This class contains tests to ensure the data retrieval functions correctly.
    """

    JSON_DATA = """{
    "waitTime": [
      {
        "hospName": "Alice Ho Miu Ling Nethersole Hospital",
        "topWait": "Over 4 hours"
      },
      {
        "hospName": "Caritas Medical Centre",
        "topWait": "Over 1 hour"
      },
      {
        "hospName": "Kwong Wah Hospital",
        "topWait": "Around 1 hour"
      }
    ],
    "updateTime": "10/6/2025 9:45pm"
  }"""

    

    

    @patch("hkopenai.hk_health_mcp_server.tools.aed_waiting.fetch_json_data")
    def test_get_aed_waiting_times(self, mock_fetch_json_data):
        """
        Test the retrieval of AED waiting times.
        Verifies that the function calls the data fetcher and returns the data with a timestamp.
        """
        mock_fetch_json_data.return_value = json.loads(self.JSON_DATA)
        with patch(
            "hkopenai.hk_health_mcp_server.tools.aed_waiting.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 7, 14, 10, 0, 0)
            mock_datetime.isoformat.return_value = "2025-07-14T10:00:00"
            result = _get_aed_waiting_times(lang="en")
            mock_fetch_json_data.assert_called_once_with(
                "https://www.ha.org.hk/opendata/aed/aedwtdata2-en.json"
            )
            self.assertIn("data", result)
            self.assertIn("last_updated", result)
            self.assertEqual(result["data"], json.loads(self.JSON_DATA))
            self.assertEqual(result["last_updated"], "2025-07-14T10:00:00")

    def test_register_tool(self):
        """
        Test the registration of the get_aed_waiting_times tool.

        This test verifies that the register function correctly registers the tool
        with the FastMCP server and that the registered tool calls the underlying
        _get_aed_waiting_times function.
        """
        mock_mcp = MagicMock()

        # Call the register function
        register(mock_mcp)

        # Verify that mcp.tool was called with the correct description
        mock_mcp.tool.assert_called_once_with(
            description="Get current Accident and Emergency Department waiting times by hospital in Hong Kong"
        )

        # Get the mock that represents the decorator returned by mcp.tool
        mock_decorator = mock_mcp.tool.return_value

        # Verify that the mock decorator was called once (i.e., the function was decorated)
        mock_decorator.assert_called_once()

        # The decorated function is the first argument of the first call to the mock_decorator
        decorated_function = mock_decorator.call_args[0][0]

        # Verify the name of the decorated function
        self.assertEqual(decorated_function.__name__, "get_aed_waiting_times")

        # Call the decorated function and verify it calls _get_aed_waiting_times
        with patch(
            "hkopenai.hk_health_mcp_server.tools.aed_waiting._get_aed_waiting_times"
        ) as mock_get_aed_waiting_times:
            decorated_function(lang="en")
            mock_get_aed_waiting_times.assert_called_once_with("en")


if __name__ == "__main__":
    unittest.main()
