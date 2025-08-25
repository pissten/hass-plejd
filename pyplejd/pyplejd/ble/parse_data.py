from .debug import rec_log

# --- TRM-01 probe helpers (temporary, logging only) --------------------------
def _u16_be(a: int, b: int) -> int:
    return (a << 8) | b

def _u16_le(a: int, b: int) -> int:
    return (b << 8) | a

def _fmt_two(v: int) -> str:
    # vis som heltall, /10 og /100 (typisk for temperatur fixed-point)
    return f"{v} ({v/10:.1f}/{v/100:.2f})"

def _probe_trm04(addr: int, b1: int, b2: int, extra: list[int], data_hex: str) -> None:
    be = _u16_be(b1, b2)
    le = _u16_le(b1, b2)
    rec_log(
        f"TRM04 b1={b1:#04x} b2={b2:#04x}  be={_fmt_two(be)}  le={_fmt_two(le)}  extra={extra}",
        addr,
    )
    rec_log(f"    {data_hex}", addr)

def _probe_trm1b(addr: int, rest: list[int], data_hex: str) -> None:
    # status-telegram med 0x1b etter 0x03 0x00 (fra loggen din)
    rec_log(f"TRM1B status rest={rest}", addr)
    rec_log(f"    {data_hex}", addr)


def parse_data(data: bytearray):
    data_bytes = [data[i] for i in range(0, len(data))]
    data_hex = "".join(f"{b:02x}" for b in data_bytes)

    match data_bytes:

        # --- TRM-01 specific frames ----------------------------------------
        case [addr, 0x01, 0x10, 0x04, 0x5C, lo, hi]:
            # Setpoint i little-endian, skalert ×10
            sp = (hi << 8) | lo
            rec_log(f"TRM01 SETPOINT = {sp} ({sp/10:.1f}°C)", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "target_temperature": sp / 10.0,
            }

        case [addr, 0x01, 0x10, 0x00, dim1, dim2, 0x80]:
            # Heating ON (eldre form)
            temp_c = dim2 - 74  # historisk heuristikk – behold som fallback
            rec_log(f"TRM01 HEATING=ON temp~={temp_c}°C (legacy)", addr)
            rec_log(f"    {data_hex}", addr)
            # Prøv å beregne fra LE også, hvis tallene gir mening
            cover_position = int.from_bytes([dim1, dim2], byteorder="little", signed=True)
            current_temperature = cover_position / 1000.0
            return {
                "address": addr,
                "current_temperature": current_temperature,
                "hvac_action": "heating",
                "hvac_mode": "heat",
                "power": True,
            }

        case [addr, 0x01, 0x10, 0x00, dim1, dim2, 0x00]:
            # Heating OFF (eldre form)
            temp_c = dim2 - 74  # historisk heuristikk – behold som fallback
            rec_log(f"TRM01 HEATING=OFF temp~={temp_c}°C (legacy)", addr)
            rec_log(f"    {data_hex}", addr)
            cover_position = int.from_bytes([dim1, dim2], byteorder="little", signed=True)
            current_temperature = cover_position / 1000.0
            return {
                "address": addr,
                "current_temperature": current_temperature,
                "hvac_action": "idle",
                "hvac_mode": "heat",
                "power": True,
            }
        # --- TRM-01 discovery/probe ------------------------------------------------

        case [addr, 0x01, 0x00, 0x04, b1, b2, *extra]:
            _probe_trm04(addr, b1, b2, extra, data_hex)
            # foreløpig ingen retur (vi bare logger)

        case [addr, 0x01, 0x01, 0x04, b1, b2, *extra]:
            _probe_trm04(addr, b1, b2, extra, data_hex)
            # foreløpig ingen retur (vi bare logger)

        case [addr, 0x01, 0x03, 0x00, 0x1B, *rest]:
            _probe_trm1b(addr, rest, data_hex)
            # foreløpig ingen retur (vi bare logger)
        # --- End TRM-01 discovery/probe --------------------------------------------


        case [0x01, 0x01, 0x10, *extra]:
            # Time data
            rec_log(f"TIME DATA {extra}", "TME")
            rec_log(f"    {data_hex}", "TME")

        case [0x02, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            # Scene update
            rec_log(f"SCENE UPDATE {scene=} {extra=}", "SCN")
            rec_log(f"    {data_hex}", "SCN")
            return {
                "scene": scene,
                "triggered": True,
            }

        case [0x00, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            # Scene triggered
            rec_log(f"SCENE TRIGGER {scene=} {extra=}", "SCN")
            rec_log(f"    {data_hex}", "SCN")
            return {
                "scene": scene,
                "triggered": True,
            }

        case [0x00, 0x01, 0x10, 0x00, 0x15, *extra]:
            # Identify buttons command
            rec_log(f"IDENTIFY BUTTON REQUEST {extra=}")
            rec_log(f"    {data_hex}")

        case [0x00, 0x01, 0x10, 0x00, 0x16, addr, button, *extra]:
            # Button pressed
            rec_log(f"BUTTON {button=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "button": button,
                "action": "release" if len(extra) and not extra[0] else "press",
            }

        case [addr, 0x01, 0x10, 0x00, 0xC8, state, dim1, dim2, *extra] | [
            addr,
            0x01,
            0x10,
            0x00,
            0x98,
            state,
            dim1,
            dim2,
            *extra,
        ]:
            # State dim command (brukes også av TRM-01)
            extra_hex = "".join(f"{e:02x}" for e in extra)
            rec_log(f"DIM {state=} {dim1=} {dim2=} {extra=} {extra_hex}", addr)

            dim = dim2
            cover_position = int.from_bytes(
                [dim1, dim2], byteorder="little", signed=True
            )
            cover_angle = None
            if extra:
                # The cover angle is given as a six bit signed number?
                cover_angle = extra[0]
                cover_angle_sign = 1
                if cover_angle & 0x20:
                    cover_angle = ~cover_angle
                    cover_angle_sign = -1
                cover_angle = (cover_angle & 0x1F) * cover_angle_sign

            current_temperature = cover_position / 1000.0  # <-- NYTTIG FOR TRM-01

            rec_log(f"    cover_position={cover_position} cover_angle={cover_angle}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "state": state,
                "dim": dim,
                "cover_position": cover_position,
                "cover_angle": cover_angle,
                "current_temperature": current_temperature,        # <-- NY
                "power": bool(state),                               # <-- NY
                "hvac_action": "heating" if state else "idle",      # <-- forsiktig default
                # NB: Vi setter ikke 'hvac_mode' her for alle enheter (kan være lys).
                # Thermostat-parse_state vil sette hvac_mode riktig basert på state.
            }

        case [addr, 0x01, 0x10, 0x00, 0x97, state, *extra]:
            # STATE-kommando (ON/OFF) – nyttig for å oppdatere climate raskt
            rec_log(f"STATE {state=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            st = 1 if state else 0
            return {
                "address": addr,
                "state": st,
                "power": bool(st),                    # <-- NY
                "hvac_mode": "heat" if st else "off", # <-- hjelper climate rett etter toggle
                "hvac_action": "heating" if st else "idle",
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x01, 0x11, *color_temp]:
            # Color temperature
            color_temp = int.from_bytes(color_temp, "big")
            rec_log(f"COLORTEMP {a}-1-11 {color_temp=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "temperature": color_temp,
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x03, b, *extra, ll1, ll2]:
            # Motion
            lightlevel = int.from_bytes([ll1, ll2], "big")
            rec_log(f"MOTION {a}-3-{b} {extra=} {lightlevel=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "motion": True,
                "luminance": lightlevel,
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x05, *extra]:
            # Off by timeout?
            rec_log(f"TIMEOUT {a=}-5 {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case [addr, 0x01, 0x10, 0x04, 0x20, *extra]:
            # Unknown new style command
            extra = [f"{e:02x}" for e in extra]
            rec_log(f"UNKNOWN NEW STYLE {addr=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case [addr, 0x01, 0x10, cmd1, cmd2, *extra]:
            # Unknown command
            cmd = (f"{cmd1:x}", f"{cmd2:x}")
            extra = [f"{e:02x}" for e in extra]
            rec_log(f"UNKNONW OLD COMMAND {addr=} {cmd=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case _:
            # Unknown command
            rec_log(f"UNKNOWN {data=}")
            rec_log(f"    {data_hex}")

    return {}