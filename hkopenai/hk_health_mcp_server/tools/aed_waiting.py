"""
Module for fetching Accident and Emergency Department (AED) waiting times
from Hospital Authority in Hong Kong.
"""

from typing import List, Dict, Optional
from datetime import datetime
from pydantic import Field
from typing_extensions import Annotated
from hkopenai_common.json_utils import fetch_json_data





def register(mcp):
    """Registers the AED waiting times tool with the FastMCP server."""

    @mcp.tool(
        description="Get current Accident and Emergency Department waiting times by hospital in Hong Kong"
    )
    def get_aed_waiting_times(
        lang: Annotated[
            Optional[str],
            Field(
                description="Language (en/tc/sc) English, Traditional Chinese, Simplified Chinese. Default English",
                json_schema_extra={"enum": ["en", "tc", "sc"]},
            ),
        ] = "en",
    ) -> Dict:
        """Get current AED waiting times

        Args:
            lang: Language code (en/tc/sc) for data format
        """
        return _get_aed_waiting_times(lang)


def _get_aed_waiting_times(lang: Optional[str] = "en") -> Dict:
    """Get current AED waiting times

    Args:
        lang: Language code (en/tc/sc) for data format
    """
    url = f"https://www.ha.org.hk/opendata/aed/aedwtdata2-{lang}.json"
    data = fetch_json_data(url)
    return {"data": data, "last_updated": datetime.now().isoformat()}
    
