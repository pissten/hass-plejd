import os
from .debug import rec_log

# Sniffer/diagnostikk for TRM. Sett PLEJD_TRM_PROBE=0 for å slå av ekstra logging.
TRM_PROBE = os.getenv("PLEJD_TRM_PROBE", "1") not in ("0", "false", "False", "")


# --------------------- Små hjelpere for logging/inspeksjon --------------------

def _u16_be(a: int, b: int) -> int:
    return (a << 8) | b

def _u16_le(a: int, b: int) -> int:
    return (b << 8) | a

def _fmt_two(v: int) -> str:
    # vis som heltall, /10 og /100 (typisk for temperatur fixed-point)
    return f"{v} ({v/10:.1f}/{v/100:.2f})"

def _probe_pair(addr: int, tag: str, a: int, b: int, data_hex: str) -> None:
    """Logg begge endian-fortolkninger + skalerte varianter for en byte-par-kandidat."""
    be = _u16_be(a, b)
    le = _u16_le(a, b)
    rec_log(f"{tag} pair a={a:#04x} b={b:#04x}  BE={_fmt_two(be)}  LE={_fmt_two(le)}", addr)
    rec_log(f"    {data_hex}", addr)

def _probe_trm04(addr: int, b1: int, b2: int, extra: list[int], data_hex: str) -> None:
    _probe_pair(addr, "TRM04", b1, b2, data_hex)
    if extra:
        rec_log(f"    extra={extra}", addr)

def _probe_trm1b(addr: int, rest: list[int], data_hex: str) -> None:
    rec_log(f"TRM1B status rest={rest}", addr)
    rec_log(f"    {data_hex}", addr)

def _scan_trm_candidates(addr: int, data_bytes: list[int], data_hex: str) -> None:
    """Heuristisk, men ren LOGG: prøv alle påfølgende bytepar i nyttelasten."""
    if not TRM_PROBE:
        return
    payload = data_bytes[1:]  # hopp over addr
    rec_log(f"TRM_SCAN len={len(payload)} bytes={payload}", addr)
    for i in range(max(0, len(payload) - 1)):
        a = payload[i]
        b = payload[i + 1]
        _probe_pair(addr, f"TRM_SCAN[{i}:{i+2}]", a, b, data_hex)


# ---------------------------------- Parser ------------------------------------

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
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
            return {
                "address": addr,
                "target_temperature": sp / 10.0,
            }

        case [addr, 0x01, 0x10, 0x00, dim1, dim2, 0x80]:
            # Heating ON (eldre form). Kun logging/tilstand – IKKE temp.
            temp_c = dim2 - 74  # historisk referanse i logg
            rec_log(f"TRM01 HEATING=ON temp~={temp_c}°C (legacy)", addr)
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
            # Heating OFF (eldre form). Kun logging/tilstand – IKKE temp.
            temp_c = dim2 - 74
            rec_log(f"TRM01 HEATING=OFF temp~={temp_c}°C (legacy)", addr)
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

        # --- TRM-01 discovery/probe ----------------------------------------
        case [addr, 0x01, 0x00, 0x04, b1, b2, *extra]:
            _probe_trm04(addr, b1, b2, extra, data_hex)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)

        case [addr, 0x01, 0x01, 0x04, b1, b2, *extra]:
            _probe_trm04(addr, b1, b2, extra, data_hex)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)

        case [addr, 0x01, 0x03, 0x00, 0x1B, *rest]:
            _probe_trm1b(addr, rest, data_hex)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
        # --- End TRM-01 discovery/probe ------------------------------------


        # --- Tid/Scene/Buttons (som før) -----------------------------------
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

        # --- “State dim” (også brukt av TRM-01). Kun logging/tilstand. -----
        case [addr, 0x01, 0x10, 0x00, 0xC8, state, dim1, dim2, *extra] | [
              addr, 0x01, 0x10, 0x00, 0x98, state, dim1, dim2, *extra]:
            extra_hex = "".join(f"{e:02x}" for e in extra)
            rec_log(f"DIM {state=} {dim1=} {dim2=} {extra=} {extra_hex}", addr)

            cover_position = int.from_bytes([dim1, dim2], byteorder="little", signed=False)
            cover_angle = None
            if extra:
                cover_angle = extra[0]
                cover_angle_sign = 1
                if cover_angle & 0x20:
                    cover_angle = ~cover_angle
                    cover_angle_sign = -1
                cover_angle = (cover_angle & 0x1F) * cover_angle_sign

            rec_log(f"    cover_position={cover_position} cover_angle={cover_angle}", addr)
            rec_log(f"    {data_hex}", addr)

            if TRM_PROBE:
                _probe_pair(addr, "TRM_DIM_LE", dim1, dim2, data_hex)
                _scan_trm_candidates(addr, data_bytes, data_hex)

            # NB: vi setter IKKE current_temperature her – kun tilstand.
            return {
                "address": addr,
                "state": state,
                "dim": dim2,
                "cover_position": cover_position,
                "cover_angle": cover_angle,
                "power": bool(state),
                "hvac_action": "heating" if state else "idle",
                "hvac_mode": "heat" if state else "off",
            }

        # --- Ren STATE (ON/OFF) ---------------------------------------------
        case [addr, 0x01, 0x10, 0x00, 0x97, state, *extra]:
            rec_log(f"STATE {state=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)
            st = 1 if state else 0
            return {
                "address": addr,
                "state": st,
                "power": bool(st),
                "hvac_mode": "heat" if st else "off",
                "hvac_action": "heating" if st else "idle",
            }

        # --- Diverse kjente (lys etc.) --------------------------------------
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

        # --- Fallback ukjent ------------------------------------------------
        case [addr, 0x01, *rest]:
            # Kan være TRM-navnerom: logg litt ekstra for analyse
            rec_log(f"UNKNOWN TRM-LIKE {addr=} rest={rest}", addr)
            rec_log(f"    {data_hex}", addr)
            if TRM_PROBE:
                _scan_trm_candidates(addr, data_bytes, data_hex)

        case [addr, 0x01, 0x10, cmd1, cmd2, *extra]:
            cmd = (f"{cmd1:x}", f"{cmd2:x}")
            extra = [f"{e:02x}" for e in extra]
            rec_log(f"UNKNONW OLD COMMAND {addr=} {cmd=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case _:
            rec_log(f"UNKNOWN {data=}")
            rec_log(f"    {data_hex}")

    return {}
