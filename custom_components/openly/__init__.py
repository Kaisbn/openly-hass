"""The Rently integration."""
from __future__ import annotations

import asyncio

from openly.cloud import RentlyCloud
from openly.devices import Lock, Thermostat
from openly.exceptions import InvalidResponseError, RentlyAuthError
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import UpdateFailed

from .config_flow import API_URL, LOGIN_URL
from .const import DOMAIN
from .coordinator import CloudCoordinator
from .climate import ClimateEntity
from .hub import HubEntity
from .lock import LockEntity

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS: list[Platform] = [Platform.LOCK, Platform.CLIMATE]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Rently component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rently from a config entry."""
    cloud = RentlyCloud(
        url=API_URL,
        login_url=LOGIN_URL,
    )

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    coordinator = CloudCoordinator(hass, cloud)
    # Initialize coordinator and login
    await coordinator.async_config_entry_first_refresh()

    try:
        async with asyncio.timeout(10):
            # Use lists as transactions
            climates = []
            locks = []
            hubs = []
            # Retrieve list of hubs from coordinator data
            for hub in coordinator.data:
                hubs.append(HubEntity(coordinator, hub.device_id))

                # Get list of devices
                devices_data = await hass.async_add_executor_job(
                    cloud.get_devices, hub.device_id
                )
                for device in devices_data:
                    if isinstance(device, Lock):
                        locks.append(LockEntity(coordinator, device.device_id))
                    if isinstance(device, Thermostat):
                        climates.append(ClimateEntity(coordinator, device.device_id))

            # Save data
            coordinator.climates = climates
            coordinator.hubs = hubs
            coordinator.locks = locks
    except RentlyAuthError as err:
        # Raising ConfigEntryAuthFailed will cancel future updates
        # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        raise ConfigEntryAuthFailed from err
    except InvalidResponseError as err:
        raise UpdateFailed("Error communicating with API") from err

    # Save as config entry data
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
