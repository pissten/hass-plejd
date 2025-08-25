# pyplejd/ble/parse_data.py
import os
from .debug import rec_log

# --- Probe toggle via env (for bred logging når vi leter etter nye felt) ----
TRM_PROBE = os.getenv("PLEJD_TRM_PROBE", "1") not in ("0", "false", "False", "")

def _u16_be(a: int, b: int) -> int:
    return (a << 8) | b

def _u16_le(a: int, b: int) -> int:
    return (b << 8) | a

def _fmt_two(v: int) -> str:
    return f"{v} ({v/10:.1f}/{v/100:.2f})"

def _probe_pair(addr: int, tag: str, a: int, b: int, data_hex: str) -> None:
    be = _u16_be(a, b)
    le = _u16_le(a, b)
    rec_log(
        f"{tag} pair a={a:#04x} b={b:#04x}  BE={_fmt_two(be)}  LE={_fmt_two(le)}",
        addr,
    )
    rec_log(f"    {data_hex}", addr)

def _scan_trm_candidates(addr: int, data_bytes: list[int], data_hex: str) -> None:
    if not TRM_PROBE:
        return
    payload = data_bytes[1:]
    rec_log(f"TRM_SCAN len={len(payload)} bytes={payload}", addr)
    for i in range(len(payload) - 1):
        a = payload[i]
        b = payload[i + 1]
        _probe_pair(addr, f"TRM_SCAN[{i}:{i+2}]", a, b, data_hex)

def parse_data(data: bytearray):
    data_bytes = [data[i] for i in range(0, len(data))]
    data_hex = "".join(f"{b:02x}" for b in data_bytes)

    match data_bytes:

        # ---------------- TRM-01 spesifikt ----------------

        # SETPOINT-rapport (bekreftet, LE ×10)
        case [addr, 0x01, 0x10, 0x04, 0x5C, lo, hi]:
            sp = (hi << 8) | lo
            rec_log(f"TRM01 SETPOINT = {sp} ({sp/10:.1f}°C)", addr)
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,
                "target_temperature": sp / 10.0,
            }

        # TRM1B-statusramme (romtemp + heating flag), observert:
        # 13 01 03 00 1b 7e 5c ac 68 01 00
        # Etter 0x1B følger: [?, t_hi, t_lo, ?, heat_flag, (ev. tail)]
        case [addr, 0x01, 0x03, 0x00, 0x1B, a, t_hi, t_lo, b, heat_flag, tail]:
            temp_milli = (t_hi << 8) | t_lo
            temp_c = temp_milli / 1000.0
            heating = bool(heat_flag)
            rec_log(
                f"TRM1B[A] temp={temp_c:.3f}°C heating={heating} "
                f"raw=[{a:#04x},{t_hi:#04x},{t_lo:#04x},{b:#04x},{heat_flag:#04x},{tail:#04x}]",
                addr,
            )
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,
                "current_temperature": temp_c,
                "hvac_action": "heating" if heating else "idle",
                "power": True,              # enheten er aktiv (kan være idle)
                "hvac_mode": "heat",
            }

        # Variant uten trailing byte
        case [addr, 0x01, 0x03, 0x00, 0x1B, a, t_hi, t_lo, b, heat_flag]:
            temp_milli = (t_hi << 8) | t_lo
            temp_c = temp_milli / 1000.0
            heating = bool(heat_flag)
            rec_log(
                f"TRM1B[B] temp={temp_c:.3f}°C heating={heating} "
                f"raw=[{a:#04x},{t_hi:#04x},{t_lo:#04x},{b:#04x},{heat_flag:#04x}]",
                addr,
            )
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,
                "current_temperature": temp_c,
                "hvac_action": "heating" if heating else "idle",
                "power": True,
                "hvac_mode": "heat",
            }

        # Broadcast/alternativ form: 00 01 10 00 1b ...
        case [addr, 0x01, 0x10, 0x00, 0x1B, a, t_hi, t_lo, b, heat_flag]:
            temp_milli = (t_hi << 8) | t_lo
            temp_c = temp_milli / 1000.0
            heating = bool(heat_flag)
            rec_log(
                f"TRM1B[C] temp={temp_c:.3f}°C heating={heating} "
                f"raw=[{a:#04x},{t_hi:#04x},{t_lo:#04x},{b:#04x},{heat_flag:#04x}] (addr={addr})",
                addr if addr else "TRM",
            )
            rec_log(f"    {data_hex}", addr if addr else "TRM")
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,  # kan være 0 (broadcast)
                "current_temperature": temp_c,
                "hvac_action": "heating" if heating else "idle",
                "power": True,
                "hvac_mode": "heat",
            }

        # Legacy “heating on/off”-rammer – nyttige for action, men IKKE for temp
        case [addr, 0x01, 0x10, 0x00, dim1, dim2, 0x80]:
            rec_log("TRM01 HEATING=ON (legacy)", addr)
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _probe_pair(addr, "TRM_DIM_LE", dim1, dim2, data_hex)
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,
                "hvac_action": "heating",
                "hvac_mode": "heat",
                "power": True,
            }

        case [addr, 0x01, 0x10, 0x00, dim1, dim2, 0x00]:
            rec_log("TRM01 HEATING=OFF (legacy)", addr)
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _probe_pair(addr, "TRM_DIM_LE", dim1, dim2, data_hex)
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,
                "hvac_action": "idle",
                "hvac_mode": "heat",
                "power": True,
            }

        # ---------------- Øvrige Plejd-rammer (som før) ----------------

        case [0x01, 0x01, 0x10, *extra]:
            rec_log(f"TIME DATA {extra}", "TME")
            rec_log(f"    {data_hex}", "TME")

        case [0x02, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            rec_log(f"SCENE UPDATE {scene=} {extra=}", "SCN")
            rec_log(f"    {data_hex}", "SCN")
            return {"scene": scene, "triggered": True}

        case [0x00, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            rec_log(f"SCENE TRIGGER {scene=} {extra=}", "SCN")
            rec_log(f"    {data_hex}", "SCN")
            return {"scene": scene, "triggered": True}

        case [0x00, 0x01, 0x10, 0x00, 0x15, *extra]:
            rec_log(f"IDENTIFY BUTTON REQUEST {extra=}")
            rec_log(f"    {data_hex}")

        case [0x00, 0x01, 0x10, 0x00, 0x16, addr, button, *extra]:
            rec_log(f"BUTTON {button=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "button": button,
                "action": "release" if len(extra) and not extra[0] else "press",
            }

        # State/dim-kommando (brukes av mange enheter, inkl. TRM, men gir ikke romtemp)
        case [addr, 0x01, 0x10, 0x00, 0xC8, state, dim1, dim2, *extra] | \
             [addr, 0x01, 0x10, 0x00, 0x98, state, dim1, dim2, *extra]:
            extra_hex = "".join(f"{e:02x}" for e in extra)
            rec_log(f"DIM {state=} {dim1=} {dim2=} {extra=} {extra_hex}", addr)
            cover_position = int.from_bytes(
                [dim1, dim2], byteorder="little", signed=False
            )
            cover_angle = None
            if extra:
                cover_angle = extra[0]
                if cover_angle & 0x20:
                    cover_angle = ~cover_angle
                    cover_angle = (cover_angle & 0x1F) * -1
                else:
                    cover_angle = (cover_angle & 0x1F)
            rec_log(f"    cover_position={cover_position} cover_angle={cover_angle}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "state": state,
                "dim": dim2,
                "cover_position": cover_position,
                "cover_angle": cover_angle,
            }

        case [addr, 0x01, 0x10, 0x00, 0x97, state, *extra]:
            rec_log(f"STATE {state=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            st = 1 if state else 0
            return {
                "address": addr,
                "state": st,
                "power": bool(st),
                "hvac_mode": "heat" if st else "off",
                "hvac_action": "heating" if st else "idle",
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x01, 0x11, *color_temp]:
            color_temp = int.from_bytes(color_temp, "big")
            rec_log(f"COLORTEMP {a}-1-11 {color_temp=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {"address": addr, "temperature": color_temp}

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x03, b, *extra, ll1, ll2]:
            lightlevel = int.from_bytes([ll1, ll2], "big")
            rec_log(f"MOTION {a}-3-{b} {extra=} {lightlevel=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {"address": addr, "motion": True, "luminance": lightlevel}

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x05, *extra]:
            rec_log(f"TIMEOUT {a=}-5 {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case [addr, 0x01, 0x10, 0x04, 0x20, *extra]:
            extra = [f"{e:02x}" for e in extra]
            rec_log(f"UNKNOWN NEW STYLE {addr=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case [addr, 0x01, 0x10, cmd1, cmd2, *extra]:
            cmd = (f"{cmd1:x}", f"{cmd2:x}")
            extra = [f"{e:02x}" for e in extra]
            rec_log(f"UNKNONW OLD COMMAND {addr=} {cmd=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case _:
            rec_log(f"UNKNOWN {data=}")
            rec_log(f"    {data_hex}")

    return {}