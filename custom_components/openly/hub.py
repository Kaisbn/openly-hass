"""Rently Hub Entity."""
from openly.devices import Hub

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Hub entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(coordinator.hubs, update_before_add=True)


class HubEntity(CoordinatorEntity):
    """An entity using CoordinatorEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available

    """

    def __init__(self, coordinator: DataUpdateCoordinator, idx: str) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator, context=idx)
        self.idx: str = idx
        self._hub: Hub = None

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        self._hub = await self.coordinator.hass.async_add_executor_job(
            self.coordinator.cloud.get_hub, self.idx
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.idx)},
            name=self._hub.home_name,
            model=self._hub.status.model,
            sw_version=self._hub.status.fmVer,
        )
