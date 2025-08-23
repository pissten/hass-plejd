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
        # TODO: Bekreft hvordan TRM-01 identifiseres fra pyplejd
        if getattr(dev, "product", None) == "TRM-01" or getattr(
            dev, "device_class", None
        ) == "thermostat":
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
        # TODO: Bytt til device.heating (bool) når pyplejd støtter det
        return HVACMode.HEAT if getattr(self.device, "heating", False) else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        # TODO: Bytt til device.current_temperature
        return getattr(self.device, "current_temperature", None)

    @property
    def target_temperature(self) -> float | None:
        # TODO: Bytt til device.target_temperature
        return getattr(self.device, "target_temperature", None)

    # --- Commands ---
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # TODO: Koble til pyplejd: device.set_mode(True/False)
        if hvac_mode == HVACMode.HEAT:
            await self.device.set_mode(True)
        else:
            await self.device.set_mode(False)

    async def async_set_temperature(self, **kwargs) -> None:
        if (t := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        # TODO: Koble til pyplejd: device.set_target_temperature(temp)
        await self.device.set_target_temperature(float(t))
