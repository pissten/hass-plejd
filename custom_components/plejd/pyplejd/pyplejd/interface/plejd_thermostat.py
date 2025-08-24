from .plejd_device import PlejdOutput, PlejdDeviceType
from .payload_encode import set_temperature as encode_set_temp

class PlejdThermostat(PlejdOutput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.CLIMATE

    def parse_state(self, update, state):
        return {
            "available": state.get("available", False),
            "current_temperature": state.get("current_temperature"),
            "target_temperature": state.get("target_temperature"),
            "hvac_mode": state.get("hvac_mode", "off"),
            "hvac_action": state.get("hvac_action", "idle"),
        }

    async def set_temperature(self, temp_c: float):
        if not self._mesh:
            return
        payloads = encode_set_temp(self._mesh, self.address, temp_c)
        await self._mesh._write(payloads)
