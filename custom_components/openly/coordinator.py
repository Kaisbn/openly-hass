"""Define a custom coordinator for Rently API communication."""
import asyncio
from datetime import timedelta
import logging

from openly.cloud import RentlyCloud
from openly.exceptions import InvalidResponseError, RentlyAPIError, RentlyAuthError

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .climate import ClimateEntity
from .const import API_LOGIN_RETRY_TIME, API_MAX_LOGIN_ATTEMPTS, DOMAIN
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
        self.climates: list[ClimateEntity] = []

    async def async_login(self):
        """Login to Rently."""
        async with asyncio.timeout(API_LOGIN_RETRY_TIME * API_MAX_LOGIN_ATTEMPTS):
            attempts = 1
            while not self.cloud.connected:
                try:
                    config_entry = self.hass.config_entries.async_entries(DOMAIN)[0]
                    connected = await self.hass.async_add_executor_job(
                        self.cloud.login,
                        config_entry.data[CONF_EMAIL],
                        config_entry.data[CONF_PASSWORD],
                    )  # only 1 entry
                    if not connected:
                        raise RentlyAuthError("Could not connect to Rently")
                except RentlyAPIError as err:
                    if attempts > API_MAX_LOGIN_ATTEMPTS:
                        raise InvalidResponseError from err
                    attempts += 1
                    asyncio.sleep(API_LOGIN_RETRY_TIME)

    async def _async_refresh(self, **kwargs):
        # Make sure user is connected
        await self.async_login()

        return await super()._async_refresh(**kwargs)

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Return list of hubs
            return await self.hass.async_add_executor_job(self.cloud.get_hubs)
        except RentlyAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except InvalidResponseError as err:
            raise UpdateFailed("Error communicating with API") from err
