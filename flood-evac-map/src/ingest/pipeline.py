"""
Ingestion pipeline — orchestrates DEM, flood, and network downloads.

Usage:
    from src.ingest.pipeline import run
    result = run()          # uses config/params.yaml by default
    result = run("path/to/other.yaml")
"""

import logging
import math
from pathlib import Path

import yaml

from . import dem as dem_mod
from . import flood as flood_mod
from . import network as net_mod

log = logging.getLogger(__name__)


def bounds_from_center(
    center_lat: float,
    center_lon: float,
    buffer_km: float,
) -> tuple:
    """
    Return (west, south, east, north) in EPSG:4326 for a square box of
    side 2 × buffer_km centred on (center_lat, center_lon).
    """
    lat_delta = buffer_km / 111.0
    lon_delta = buffer_km / (111.0 * math.cos(math.radians(center_lat)))
    return (
        center_lon - lon_delta,   # west
        center_lat - lat_delta,   # south
        center_lon + lon_delta,   # east
        center_lat + lat_delta,   # north
    )


def run(config_path: str = "config/params.yaml") -> dict:
    """
    Run all ingestion steps.

    Returns a dict with keys:
        bounds    – (west, south, east, north)
        dem       – Path to clipped DEM GeoTIFF
        flood     – Path to clipped flood-occurrence GeoTIFF
        roads     – Path to roads GeoPackage
        waterways – Path to waterways GeoPackage
    """
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config not found: {cfg_file.resolve()}")

    with cfg_file.open() as fh:
        cfg = yaml.safe_load(fh)

    aoi = cfg["aoi"]
    paths = cfg["paths"]

    center_lat: float = aoi["center_lat"]
    center_lon: float = aoi["center_lon"]
    buffer_km: float = aoi["buffer_km"]

    bounds = bounds_from_center(center_lat, center_lon, buffer_km)
    log.info(
        "PIPELINE | AOI  W=%.4f  S=%.4f  E=%.4f  N=%.4f  (buffer=%g km)",
        *bounds, buffer_km,
    )

    # Resolve all paths relative to the config file's parent directory
    base = cfg_file.parent.parent  # project root
    def p(key: str) -> Path:
        return base / paths[key]

    result: dict = {"bounds": bounds}

    log.info("PIPELINE | step 1/4 - DEM")
    result["dem"] = dem_mod.download(bounds, p("raw_dem"))

    log.info("PIPELINE | step 2/4 - flood occurrence")
    result["flood"] = flood_mod.download(bounds, p("raw_flood"))

    log.info("PIPELINE | step 3/4 - road network")
    result["roads"] = net_mod.download_roads(
        center_lat, center_lon, buffer_km, p("raw_roads")
    )

    log.info("PIPELINE | step 4/4 - waterways")
    result["waterways"] = net_mod.download_waterways(
        center_lat, center_lon, buffer_km, p("raw_hydro")
    )

    log.info("PIPELINE | ingestion complete")
    return result
