"""Climate platform for Rently devices."""
import asyncio
from datetime import timedelta
from enum import StrEnum

from openly.devices import Thermostat
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    UnitOfTemperature
)

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACMode,
    ClimateEntity as BaseClimateEntity,
    FAN_ON,
    FAN_AUTO
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CLIMATE_MAX_REFRESH_ATTEMPTS,
    CLIMATE_MIN_TEMP_SPREAD,
    CLIMATE_UPDATE_DELAY,
    DOMAIN,
)
from .exceptions import DeviceNotFoundError, StateNotSupportedError


# Poll every minute
SCAN_INTERVAL = timedelta(seconds=60)

class FanMode(StrEnum):
    """Fan mode for climate devices."""
    ON = FAN_ON
    AUTO = FAN_AUTO

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Hub entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(coordinator.climates, update_before_add=True)


class ClimateEntity(CoordinatorEntity, BaseClimateEntity):
    """Rently Climate Entity implementing climate control."""
    _attr_supported_features: ClimateEntityFeature = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
    _attr_force_update: bool = False
    _climate: Thermostat | None = None

    def __init__(self, coordinator: DataUpdateCoordinator, idx: str) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator, context=idx)
        self.idx: str = idx
        self._attr_unique_id = f"rently-climate-{idx}"
        self._state = None

    async def async_update(self) -> None:
        """Fetch the entity from the server."""
        self._climate = await self.async_get_status()
        if self._climate:
            self._state = self._climate.mode

    async def async_get_status(self) -> Thermostat:
        """Fetch device status from the server"""
        return await self.hass.async_add_executor_job(
            self.coordinator.cloud.get_device, self.idx
        )

    # Properties
    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._climate.name

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.idx)},
            name=self.name,
            manufacturer=self._climate.manufacturer,
            model=self._climate.product_name,
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes of the last update."""
        return {
            ATTR_BATTERY_LEVEL: self._climate.battery if self._climate else None,
        }

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.FAHRENHEIT # TODO: Add support for all units

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._climate.room_temp if self._climate else None

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode."""
        return self._climate.fan if self._climate else None

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the list of available fan modes."""
        return self._climate.fan_modes if self._climate else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        return self._climate.mode if self._climate else None

    @property
    def hvac_modes(self) -> list[HVACMode] | None:
        """Return the list of available HVAC modes."""
        return self._climate.modes if self._climate else None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the high target temperature."""
        return self._climate.cooling_setpoint if self._climate else None

    @property
    def target_temperature_low(self) -> float | None:
        """Return the low target temperature."""
        return self._climate.heating_setpoint if self._climate else None

    async def async_save_state(self) -> None:
        """Send climate state to API"""
        await self.hass.async_add_executor_job(
            self.coordinator.cloud.update_device_status, self._climate
        )
        self.async_write_ha_state() # no await

        attempts = 1
        while attempts < CLIMATE_MAX_REFRESH_ATTEMPTS:
            attempts += 1
            # Wait for command to complete
            await asyncio.sleep(CLIMATE_UPDATE_DELAY)
            # Stop the loop when device is updated
            new_state = self.async_get_status()
            if new_state.mode != self.hvac_mode or new_state.fan != self.fan_mode or new_state.target_temperature_high != self.cooling_setpoint or new_state.target_temperature_low != self.heating_setpoint:
              continue
            break

    async def async_set_temperature_range(self, low: float, high: float) -> None:
        """Set temperature range"""
        self._climate.heating_setpoint, self._climate.cooling_setpoint = low, high
        await self.async_save_state()

    # Setters
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if not self._climate:
            raise DeviceNotFoundError
        if hvac_mode not in self.hvac_modes:
            raise StateNotSupportedError

        # Set status
        self._climate.mode = hvac_mode
        # Send command
        await self.async_save_state()

    async def aync_turn_on(self) -> None:
        """Turn the HVAC on"""
        self.async_set_hvac_mode(HVACMode.ON)

    async def aync_turn_off(self) -> None:
        """Turn the HVAC off"""
        self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: FanMode) -> None:
        """Set new fan mode"""
        if not self._climate:
            raise DeviceNotFoundError

        if fan_mode not in self.fan_modes:
            raise StateNotSupportedError

        # Set status
        self._climate.fan = fan_mode
        # Send command
        await self.async_save_state()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature"""
        temperature_low = int(float(kwargs.get(ATTR_TARGET_TEMP_LOW)))
        temperature_high = int(float(kwargs.get(ATTR_TARGET_TEMP_HIGH)))

        # Temperature
        if self.hvac_mode == HVACMode.COOL and temperature_high:
            await self.async_set_temperature_range(temperature_high - CLIMATE_MIN_TEMP_SPREAD, temperature_high)
        elif self.hvac_mode == HVACMode.HEAT and temperature_low:
            await self.async_set_temperature_range(temperature_low, temperature_low + CLIMATE_MIN_TEMP_SPREAD)
        elif self.hvac_mode == HVACMode.AUTO:
          await self.async_set_temperature_range(temperature_low, temperature_high)
