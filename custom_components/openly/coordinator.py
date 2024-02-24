"""Define a custom coordinator for Rently API communication."""
import asyncio
from datetime import timedelta
import logging

from openly.cloud import RentlyCloud
from openly.exceptions import InvalidResponseError, RentlyAuthError

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .hub import HubEntity
from .lock import LockEntity

_LOGGER = logging.getLogger(__name__)


class CloudCoordinator(DataUpdateCoordinator):
    """Coordinator for Rently API.."""

    def __init__(self, hass: HomeAssistant, cloud: RentlyCloud) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Rently Hubs",
            # Polling interval. Hubs are rarely updated. 15 minutes is reasonable.
            update_interval=timedelta(seconds=900),
        )
        self.cloud = cloud
        self.hubs: list[HubEntity] = []
        self.locks: list[LockEntity] = []

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            async with asyncio.timeout(10):
                # Get list of hubs
                return await self.hass.async_add_executor_job(self.cloud.get_hubs)
        except RentlyAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except InvalidResponseError as err:
            raise UpdateFailed("Error communicating with API") from err
