"""Exceptions for the Rently integration."""
from homeassistant.exceptions import HomeAssistantError


class DeviceNotFoundError(HomeAssistantError):
    """Error to indicate device not found."""

class StateNotSupportedError(HomeAssistantError):
    """Error to indicate state not supported."""
