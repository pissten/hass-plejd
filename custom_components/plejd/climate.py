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


def _id_of(dev: dt.PlejdDevice) -> str:
    """Robust uthenting av et identifiserende id for logging/unique_id."""
    pid = getattr(dev, "devId", None)
    if pid in (None, "?", ""):
        pid = (
            getattr(dev, "index", None)
            or getattr(dev, "device_index", None)
            or getattr(dev, "device_id", None)
            or getattr(dev, "address", None)
        )
    return str(pid) if pid is not None else "?"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Plejd TRM-01 thermostats from a config entry."""
    site = get_plejd_site_from_config_entry(hass, entry)
    entities: list[PlejdThermostatEntity] = []

    # Eksisterende enheter ved oppstart
    for dev in site.devices:
        if getattr(dev, "outputType", None) == dt.PlejdDeviceType.CLIMATE or dev.__class__.__name__ == "PlejdThermostat":
            entities.append(PlejdThermostatEntity(dev))
            _LOGGER.debug(
                "Registering climate for Plejd id=%s name=%s (startup)",
                _id_of(dev),
                getattr(dev, "name", "?"),
            )

    if entities:
        async_add_entities(entities)
        _LOGGER.debug("Added %d Plejd climate entities at startup", len(entities))

    # Nye enheter som dukker opp senere
    def _adder(dev: dt.PlejdDevice) -> None:
        if getattr(dev, "outputType", None) == dt.PlejdDeviceType.CLIMATE or dev.__class__.__name__ == "PlejdThermostat":
            ent = PlejdThermostatEntity(dev)
            async_add_entities([ent])
            _LOGGER.debug(
                "Registering climate for Plejd id=%s name=%s (runtime)",
                _id_of(dev),
                getattr(dev, "name", "?"),
            )

    site.register_platform_add_device_callback(_adder, dt.PlejdDeviceType.CLIMATE)


class PlejdThermostatEntity(PlejdDeviceBaseEntity, ClimateEntity):
    """Representation of a Plejd TRM-01 thermostat."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5.0
    _attr_max_temp = 40.0
    _attr_precision = 1.0

    def __init__(self, device: dt.PlejdDevice) -> None:
        super().__init__(device)
        self._attr_name = device.name
        self._hvac_mode: HVACMode | None = None  # lokal cache

    def _resolve_plejd_id(self) -> str:
        return _id_of(self.device)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _LOGGER.debug(
            "Climate entity added: entity_id=%s for Plejd id=%s name=%s",
            self.entity_id,
            self._resolve_plejd_id(),
            getattr(self.device, "name", "?"),
        )

    # --- State ---

    @property
    def hvac_mode(self) -> HVACMode:
        # Bruk cache hvis satt
        if self._hvac_mode is not None:
            return self._hvac_mode

        # Les parserens verdi hvis satt
        mode = self.device._state.get("hvac_mode", "off")
        try:
            return HVACMode(mode)
        except Exception:
            # Fallback: avled fra device power/state
            dev_power = getattr(self.device, "power", None)
            if dev_power is None:
                dev_power = getattr(self.device, "state", None)
            return HVACMode.HEAT if bool(dev_power) else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        # 1) bruk parserens verdi hvis satt
        action = self.device._state.get("hvac_action")
        if action:
            try:
                return HVACAction(action)
            except Exception:
                pass
        # 2) fallback fra TRM state (1=heating, 0=idle)
        trm_state = self.device._state.get("trm_state")
        if trm_state == 1:
            return HVACAction.HEATING
        if trm_state == 0:
            return HVACAction.IDLE
        # 3) avled fra hvac_mode
        return HVACAction.OFF if self.hvac_mode == HVACMode.OFF else HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self.device._state.get("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self.device._state.get("target_temperature")

    # --- Commands ---

    async def async_set_temperature(self, **kwargs) -> None:
        t = kwargs.get(ATTR_TEMPERATURE)
        if t is None:
            return
        t = float(t)
        _LOGGER.debug(
            "Set target_temperature=%.1f on Plejd id=%s",
            t,
            self._resolve_plejd_id(),
        )
        await self.device.set_temperature(t)

    async def _set_power(self, on: bool) -> None:
        """Best-effort: slå TRM på/av uten å anta eksakt pyplejd-API."""
        dev = self.device
        pid = self._resolve_plejd_id()

        try:
            if hasattr(dev, "set_power"):
                _LOGGER.debug("[plejd.climate] (%s) set_power(%s)", pid, on)
                await self.hass.async_add_executor_job(dev.set_power, on)
            elif on and hasattr(dev, "turn_on"):
                _LOGGER.debug("[plejd.climate] (%s) turn_on()", pid)
                await self.hass.async_add_executor_job(dev.turn_on)
            elif not on and hasattr(dev, "turn_off"):
                _LOGGER.debug("[plejd.climate] (%s) turn_off()", pid)
                await self.hass.async_add_executor_job(dev.turn_off)
            elif hasattr(dev, "set_state"):
                _LOGGER.debug("[plejd.climate] (%s) set_state(%s)", pid, on)
                await self.hass.async_add_executor_job(dev.set_state, on)
            else:
                _LOGGER.warning(
                    "[plejd.climate] (%s) Ingen power-metode på device; kan ikke sette HVAC ON/OFF",
                    pid,
                )
                return
        finally:
            # Tving en refresh etter kommando
            try:
                await self.async_update_ha_state(True)
            except Exception as e:
                _LOGGER.debug("[plejd.climate] (%s) async_update_ha_state error: %s", pid, e)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        _LOGGER.debug(
            "Set hvac_mode=%s on Plejd id=%s",
            hvac_mode,
            self._resolve_plejd_id(),
        )

        # Map HA-modus til power ON/OFF
        if hvac_mode == HVACMode.OFF:
            await self._set_power(False)
            self._hvac_mode = HVACMode.OFF
        elif hvac_mode in (HVACMode.HEAT, HVACMode.AUTO):
            # Ingen egen AUTO i TRM; behandle som HEAT=ON
            await self._set_power(True)
            self._hvac_mode = HVACMode.HEAT
        else:
            raise NotImplementedError(f"HVAC mode {hvac_mode} not supported")

        # Oppdater UI umiddelbart
        await self.async_update_ha_state(True)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
