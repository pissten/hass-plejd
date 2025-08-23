from __future__ import annotations
import logging
from typing import Type

from . import device_type as DeviceTypes
from ..cloud import PlejdEntityData, PlejdSceneData

_LOGGER = logging.getLogger(__name__)
dt = DeviceTypes


def outputDeviceClass(device: PlejdEntityData) -> Type[dt.PlejdDevice]:
    # Følger eksisterende prioritet først
    if device["plejdDevice"].isFellowshipFollower:
        return dt.PlejdFellowshipFollower

    tpe = device["device"].outputType
    if tpe == "LIGHT":
        return dt.PlejdLight
    if tpe == "RELAY":
        return dt.PlejdRelay
    if tpe == "COVERABLE":
        return dt.PlejdCover

    # --- TRM-01 / CLIMATE deteksjon FØR POWER/DIM-fallback ---
    traits = dt.PlejdTraits(device["device"].traits)

    # Noen installasjoner har nyttig info i disse feltene:
    hw_notes = (getattr(device["plejdDevice"].firmware, "notes", "") or "").upper()
    hw_name  = (getattr(device["plejdDevice"], "hardwareName", "") or "").upper()
    product  = (getattr(device["plejdDevice"], "product", "") or "").upper()

    is_trm = (
        "TRM" in hw_notes
        or "TRM" in hw_name
        or "TRM" in product
        or (hasattr(dt.PlejdTraits, "TEMP") and dt.PlejdTraits.TEMP in traits)
    )

    if is_trm:
        _LOGGER.debug(
            "Classify TRM/CLIMATE: id=%s name=%s traits=%s notes=%s hw=%s product=%s",
            getattr(device["plejdDevice"], "id", "?"),
            getattr(device["plejdDevice"], "name", "?"),
            list(traits), hw_notes, hw_name, product,
        )
        return dt.PlejdThermostat
    # ---------------------------------------------------------

    # Vanlig fallback basert på traits
    if dt.PlejdTraits.COVER in traits:
        return dt.PlejdCover
    if dt.PlejdTraits.POWER in traits:
        if dt.PlejdTraits.DIM in traits:
            return dt.PlejdLight
        return dt.PlejdRelay

    return dt.PlejdDevice


def inputDeviceClass(device: PlejdEntityData) -> Type[dt.PlejdDevice]:
    if device["motion"]:
        return dt.PlejdMotionSensor
    return dt.PlejdButton


def sceneDeviceClass(device: PlejdSceneData) -> Type[dt.PlejdDevice]:
    return dt.PlejdScene