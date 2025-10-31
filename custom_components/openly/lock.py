"""Rently Lock Entity."""
import asyncio
from datetime import timedelta
from typing import Any
from venv import logger

from openly.devices import Lock

from homeassistant.components.lock import LockEntity as BaseLockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL
)

from homeassistant.components.lock import (
    LockEntityFeature,
    STATE_JAMMED,
    STATE_LOCKED,
    STATE_LOCKING,
    STATE_UNAVAILABLE,
    STATE_UNLOCKING,
    STATE_OPEN
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, LOCK_MAX_REFRESH_ATTEMPTS, LOCK_UPDATE_DELAY

# Poll every minute
SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Hub entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(coordinator.locks, update_before_add=True)


class LockEntity(CoordinatorEntity, BaseLockEntity):
    """Rently Lock Entity implementing lock/unlock."""

    _attr_supported_features: LockEntityFeature = LockEntityFeature.OPEN
    _attr_force_update: bool = False
    _lock: Lock | None = None

    def __init__(self, coordinator: DataUpdateCoordinator, idx: str) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator, context=idx)
        self.idx: str = idx
        self._attr_unique_id = f"rently-{idx}"
        self._state = STATE_UNAVAILABLE

    async def async_get_lock_status(self) -> bool:
        """Retrieve the lock status."""
        lock = await self.hass.async_add_executor_job(
            self.coordinator.cloud.get_device, self.idx
        )

        return lock.mode == STATE_LOCKED

    async def async_update(self) -> None:
        """Update the entity from the server."""
        self._lock = await self.hass.async_add_executor_job(
            self.coordinator.cloud.get_device, self.idx
        )
        if not self._lock:
            if self.available:
                logger.error("Lock not found")
            self._attr_available = False
            return

        self._attr_available = True
        self._attr_extra_state_attributes = {
            ATTR_BATTERY_LEVEL: self._lock.battery,
        }
        self._state = self._lock.mode

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._attr_available

    @property
    def name(self) -> str:
        """Return the name of the lock."""
        return self._lock.name

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.idx)},
            name=self.name,
            manufacturer=self._lock.manufacturer,
            model=self._lock.product_name,
        )

    @property
    def is_locked(self) -> bool:
        """Return true if lock is locked."""
        return self._state == STATE_LOCKED

    @property
    def is_jammed(self) -> bool:
        """Return true if lock is jammed."""
        return self._state == STATE_JAMMED

    @property
    def is_locking(self) -> bool:
        """Return true if lock is locking."""
        return self._state == STATE_LOCKING

    @property
    def is_unlocking(self) -> bool:
        """Return true if lock is unlocking."""
        return self._state == STATE_UNLOCKING

    @property
    def is_open(self) -> bool:
        """Return true if lock is unlatched."""
        return self._state == STATE_OPEN

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        if not self._lock:
            raise DeviceNotFoundError
        self._state = STATE_LOCKING
        self.async_write_ha_state()
        # Set status
        self._lock.lock()
        # Send command
        await self.hass.async_add_executor_job(
            self.coordinator.cloud.update_device_status, self._lock
        )

        attempts = 1
        while attempts < LOCK_MAX_REFRESH_ATTEMPTS:
            # Wait for command to complete
            await asyncio.sleep(LOCK_UPDATE_DELAY)
            # Stop the loop when device is locked
            locked = await self.async_get_lock_status()
            if locked:
                break
            attempts += 1

        # final update
        await self.async_device_update()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Lock the device."""
        if not self._lock:
            raise DeviceNotFoundError
        self._state = STATE_UNLOCKING
        self.async_write_ha_state()
        # Set status
        self._lock.unlock()
        # Send command
        await self.hass.async_add_executor_job(
            self.coordinator.cloud.update_device_status, self._lock
        )

        attempts = 1
        while attempts < LOCK_MAX_REFRESH_ATTEMPTS:
            # Wait for command to complete
            await asyncio.sleep(LOCK_UPDATE_DELAY)
            # Stop the loop when device is unlocked
            locked = await self.async_get_lock_status()
            if not locked:
                break
            attempts += 1

        # final update
        await self.async_device_update()


class DeviceNotFoundError(HomeAssistantError):
    """Error to indicate device not found."""
