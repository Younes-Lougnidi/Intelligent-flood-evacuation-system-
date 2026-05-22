"""
Slope computation from a DEM GeoTIFF.

Uses numpy.gradient to compute rise/run in x and y directions, then converts
to degrees.  Pixel size is converted to metres accounting for latitude so the
result is geometrically correct for geographic (EPSG:4326) rasters.
"""

import logging
import math
from pathlib import Path

import numpy as np
import rasterio

log = logging.getLogger(__name__)


def compute(dem_path: Path, output_dir: Path) -> Path:
    """
    Compute slope (degrees) from dem_path and write slope.tif to output_dir.
    Returns the output path.
    """
    dem_path = Path(dem_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "slope.tif"

    if out_path.exists():
        log.info("SLOPE | cache hit -> %s", out_path)
        return out_path

    with rasterio.open(dem_path) as src:
        elev = src.read(1).astype("float32")
        nodata = src.nodata
        transform = src.transform
        meta = src.meta.copy()
        center_lat = (src.bounds.top + src.bounds.bottom) / 2.0

    if nodata is not None:
        elev[elev == nodata] = np.nan

    # Pixel dimensions in metres (geographic CRS correction)
    px_deg = abs(transform.a)
    py_deg = abs(transform.e)
    dx_m = px_deg * 111_320.0 * math.cos(math.radians(center_lat))
    dy_m = py_deg * 111_320.0

    dz_dy, dz_dx = np.gradient(elev, dy_m, dx_m)
    slope_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
    slope_deg = np.degrees(slope_rad).astype("float32")
    slope_deg[np.isnan(elev)] = np.nan

    meta.update(dtype="float32", nodata=float("nan"), count=1)
    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(slope_deg, 1)

    log.info(
        "SLOPE | saved slope.tif  (mean=%.1f deg  max=%.1f deg)",
        float(np.nanmean(slope_deg)),
        float(np.nanmax(slope_deg)),
    )
    return out_path
