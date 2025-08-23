from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, HVACMode
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .plejd_site import dt, get_plejd_site_from_config_entry
from .plejd_entity import PlejdDeviceBaseEntity

SUPPORTED_HVAC_MODES = [HVACMode.HEAT, HVACMode.OFF]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Plejd TRM-01 thermostats from a config entry."""
    site = get_plejd_site_from_config_entry(hass, entry)
    entities: list[PlejdThermostatEntity] = []

    for dev in site.devices:
        # Bruk outputType=CLIMATE fra pyplejd for å finne termostater
        if getattr(dev, "outputType", None) == dt.PlejdDeviceType.CLIMATE:
            entities.append(PlejdThermostatEntity(dev))

    if entities:
        async_add_entities(entities)


class PlejdThermostatEntity(PlejdDeviceBaseEntity, ClimateEntity):
    """Representation of a Plejd TRM-01 thermostat."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5.0
    _attr_max_temp = 40.0

    def __init__(self, device: dt.PlejdDevice) -> None:
        super().__init__(device)
        self._attr_name = device.name

    # --- State properties ---
    @property
    def hvac_mode(self) -> HVACMode:
        # Bruker felt fra parse_data → PlejdThermostat.parse_state
        return HVACMode(self.device._state.get("hvac_mode", "off"))

    @property
    def hvac_action(self) -> str:
        return self.device._state.get("hvac_action", "idle")

    @property
    def current_temperature(self) -> float | None:
        return self.device._state.get("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self.device._state.get("target_temperature")

    # --- Commands ---
    async def async_set_temperature(self, **kwargs) -> None:
        if (t := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.device.set_temperature(float(t))
