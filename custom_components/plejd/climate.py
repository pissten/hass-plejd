from __future__ import annotations

import logging
from typing import List

from homeassistant.components.climate import ClimateEntity, HVACMode, HVACAction
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .plejd_site import dt, get_plejd_site_from_config_entry
from .plejd_entity import PlejdDeviceBaseEntity

_LOGGER = logging.getLogger(__name__)

SUPPORTED_HVAC_MODES: List[HVACMode] = [HVACMode.HEAT, HVACMode.OFF]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Plejd TRM-01 thermostats from a config entry."""
    site = get_plejd_site_from_config_entry(hass, entry)
    entities: list[PlejdThermostatEntity] = []

    # 1) Eksisterende enheter ved oppstart
    for dev in site.devices:
        if getattr(dev, "outputType", None) == dt.PlejdDeviceType.CLIMATE or dev.__class__.__name__ == "PlejdThermostat":
            entities.append(PlejdThermostatEntity(dev))
            _LOGGER.debug(
                "Registering climate for Plejd id=%s name=%s (startup)",
                getattr(dev, "devId", "?"),
                getattr(dev, "name", "?"),
            )

    if entities:
        async_add_entities(entities)
        _LOGGER.debug("Added %d Plejd climate entities at startup", len(entities))

    # 2) Nye enheter som dukker opp senere (f.eks. etter reconnect)
    def _adder(dev: dt.PlejdDevice) -> None:
        if getattr(dev, "outputType", None) == dt.PlejdDeviceType.CLIMATE or dev.__class__.__name__ == "PlejdThermostat":
            ent = PlejdThermostatEntity(dev)
            async_add_entities([ent])
            _LOGGER.debug(
                "Registering climate for Plejd id=%s name=%s (runtime)",
                getattr(dev, "devId", "?"),
                getattr(dev, "name", "?"),
            )

    site.register_platform_add_device_callback(_adder, dt.PlejdDeviceType.CLIMATE)


class PlejdThermostatEntity(PlejdDeviceBaseEntity, ClimateEntity):
    """Representation of a Plejd TRM-01 thermostat."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # TRM-01 område
    _attr_min_temp = 5.0
    _attr_max_temp = 40.0
    # Bruk én desimal (HA håndterer presisjon selv, men greit å være eksplisitt)
    _attr_precision = 1.0

    def __init__(self, device: dt.PlejdDevice) -> None:
        super().__init__(device)
        self._attr_name = device.name

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _LOGGER.debug(
            "Climate entity added: entity_id=%s for Plejd id=%s name=%s",
            self.entity_id,
            getattr(self._device, "devId", "?"),
            getattr(self._device, "name", "?"),
        )

    # --- State properties ---

    @property
    def hvac_mode(self) -> HVACMode:
        # settes i PlejdThermostat.parse_state(...)
        mode = self.device._state.get("hvac_mode", "off")
        try:
            return HVACMode(mode)
        except Exception:
            return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        # optional – vises som heating/idle/off i UI
        action = self.device._state.get("hvac_action", "idle")
        try:
            return HVACAction(action)
        except Exception:
            # Hvis underliggende state ikke følger enum-verdier, bare ikke rapportér action
            return None

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
        t = float(t)
        _LOGGER.debug(
            "Set target_temperature=%.1f on Plejd id=%s",
            t,
            getattr(self._device, "devId", "?"),
        )
        await self.device.set_temperature(t)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # Under ligger en enkel mapping i PlejdThermostat.set_hvac_mode(...)
        # som håndterer OFF/HEAT → korrekt skriv mot enheten.
        _LOGGER.debug(
            "Set hvac_mode=%s on Plejd id=%s",
            hvac_mode,
            getattr(self._device, "devId", "?"),
        )
        await self.device.set_hvac_mode(str(hvac_mode.value))

    # (valgfritt) Flere convenience-metoder som enkelte integrasjoner bruker
    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)