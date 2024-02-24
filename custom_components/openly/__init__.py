"""The Rently integration."""
from __future__ import annotations

import asyncio

from openly.cloud import RentlyCloud
from openly.devices import Lock
from openly.exceptions import (
    InvalidResponseError,
    MissingParametersError,
    RentlyAuthError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import UpdateFailed

from .config_flow import API_URL, LOGIN_URL, CannotConnect, InvalidAuth
from .const import DOMAIN
from .coordinator import CloudCoordinator
from .hub import HubEntity
from .lock import LockEntity

PLATFORMS: list[Platform] = [Platform.LOCK]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rently from a config entry."""
    cloud = RentlyCloud(
        url=API_URL,
        login_url=LOGIN_URL,
    )

    try:
        await hass.async_add_executor_job(
            cloud.login, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
        )
    except RentlyAuthError as err:
        raise InvalidAuth from err
    except MissingParametersError as err:
        raise CannotConnect from err

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    coordinator = CloudCoordinator(hass, cloud)
    await coordinator.async_config_entry_first_refresh()

    try:
        async with asyncio.timeout(10):
            # Get list of hubs
            lock_devices = []
            hub_devices = await hass.async_add_executor_job(cloud.get_hubs)
            for hub in hub_devices:
                # Get list of devices
                devices_data = await hass.async_add_executor_job(
                    cloud.get_devices, hub.id
                )

                for device in devices_data:
                    if isinstance(device, Lock):
                        lock_devices.append(device)

            # Create HubCoordinator for each hub
            coordinator.hubs = [HubEntity(coordinator, hub.id) for hub in hub_devices]

            coordinator.locks = [
                LockEntity(coordinator, lock.id) for lock in lock_devices
            ]
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
