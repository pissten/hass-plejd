from .plejd_device import PlejdOutput, PlejdDeviceType
from ..ble.payload_encode import set_temperature as encode_set_temp
from ..ble.payload_encode import set_state as encode_set_state  # <-- NY

class PlejdThermostat(PlejdOutput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.CLIMATE

    def parse_state(self, update, state):
        """
        Map innkommende TRM-oppdateringer til klima-state.
        - target_temperature fra SETPOINT-ramme
        - current_temperature fra cover_position/1000
        - power/hvac_mode/hvac_action fra state (0/1)
        """
        # Start med eksisterende verdier
        current_temperature = state.get("current_temperature")
        target_temperature = state.get("target_temperature")
        hvac_mode = state.get("hvac_mode", "off")
        hvac_action = state.get("hvac_action", "idle")
        power = state.get("power")

        # Bruk nye oppdateringer fra BLE-parseren
        if update:
            # Nytt settpunkt rapportert
            if "target_temperature" in update:
                target_temperature = update["target_temperature"]

            # TRM-status: cover_position = temp * 1000 (LE)
            if "cover_position" in update and update["cover_position"] is not None:
                try:
                    current_temperature = float(update["cover_position"]) / 1000.0
                except Exception:
                    pass
            elif "current_temperature" in update:
                # Fallback hvis parser allerede har satt current_temperature
                current_temperature = update["current_temperature"]

            # Strøm/power og hvac
            if "state" in update:
                st = 1 if update["state"] else 0
                power = bool(st)
                hvac_mode = "heat" if st else "off"
                # Uten mer detalj får vi anta heating når state=1, ellers idle/off
                hvac_action = "heating" if st else "idle"

            # Hvis parser eksplisitt satte disse, bruk dem
            if "hvac_mode" in update:
                hvac_mode = update["hvac_mode"]
            if "hvac_action" in update:
                hvac_action = update["hvac_action"]

        return {
            "available": state.get("available", False),
            "current_temperature": current_temperature,
            "target_temperature": target_temperature,
            "hvac_mode": hvac_mode,
            "hvac_action": hvac_action,
            "power": power,  # nyttig for climate.py sin fallback
        }

    async def set_temperature(self, temp_c: float):
        if not self._mesh:
            return
        payloads = encode_set_temp(self._mesh, self.address, temp_c)
        await self._mesh._write(payloads)

    async def set_power(self, on: bool):  # <-- NY
        """
        Slå TRM-01 av/på via 0x0097 "STATE" kommando:
          ON: AA 0110 0097 01
          OFF: AA 0110 0097 00
        """
        if not self._mesh:
            return
        payloads = encode_set_state(self._mesh, self.address, state=1 if on else 0)
        await self._mesh._write(payloads)