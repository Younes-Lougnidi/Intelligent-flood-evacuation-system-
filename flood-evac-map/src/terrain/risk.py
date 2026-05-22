"""
Flood risk score computation.

Combines three layers into a single 0-1 risk raster:
  - flood occurrence  (50 % weight) -- JRC GSW historical flood frequency
  - low elevation     (30 % weight) -- low ground floods first
  - slope             (20 % weight) -- steep slopes block safe evacuation routes

The flood and slope rasters are reprojected to the DEM grid before combining.
Output pixel values: 0.0 = no risk, 1.0 = maximum risk.
"""

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

log = logging.getLogger(__name__)

_W_FLOOD = 0.50
_W_ELEV  = 0.30
_W_SLOPE = 0.20


def _norm(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((arr - lo) / (hi - lo + 1e-9), 0.0, 1.0)


def _reproject_to_ref(
    src_path: Path,
    ref_transform,
    ref_crs,
    ref_shape: tuple,
) -> np.ndarray:
    with rasterio.open(src_path) as src:
        out = np.empty(ref_shape, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            resampling=Resampling.bilinear,
        )
    return out


def compute(
    dem_path: Path,
    slope_path: Path,
    flood_path: Path,
    output_dir: Path,
) -> Path:
    """
    Produce risk_score.tif in output_dir.
    Returns the output path.
    """
    dem_path   = Path(dem_path)
    slope_path = Path(slope_path)
    flood_path = Path(flood_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "risk_score.tif"

    if out_path.exists():
        log.info("RISK  | cache hit -> %s", out_path)
        return out_path

    # DEM is the reference grid
    with rasterio.open(dem_path) as src:
        elev = src.read(1).astype("float32")
        nodata = src.nodata
        ref_transform = src.transform
        ref_crs = src.crs
        ref_shape = (src.height, src.width)
        meta = src.meta.copy()

    if nodata is not None:
        elev[elev == nodata] = np.nan

    # Reproject flood and slope onto DEM grid
    flood = _reproject_to_ref(flood_path, ref_transform, ref_crs, ref_shape)
    slope = _reproject_to_ref(slope_path, ref_transform, ref_crs, ref_shape)

    # JRC nodata = 255 -> treat as never flooded (0)
    flood[flood >= 254] = 0.0
    flood = np.clip(flood, 0.0, 100.0)

    # Percentile-based normalisation to be robust against outliers
    elev_lo, elev_hi   = np.nanpercentile(elev,  [2, 98])
    slope_hi           = float(np.nanpercentile(slope, 98))

    flood_norm = _norm(flood, 0.0, 100.0)
    elev_norm  = 1.0 - _norm(elev, elev_lo, elev_hi)   # low elevation = high risk
    slope_norm = _norm(slope, 0.0, slope_hi)

    risk = (
        _W_FLOOD * flood_norm +
        _W_ELEV  * elev_norm  +
        _W_SLOPE * slope_norm
    ).astype("float32")

    risk[np.isnan(elev)] = float("nan")

    meta.update(dtype="float32", nodata=float("nan"), count=1)
    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(risk, 1)

    log.info(
        "RISK  | saved risk_score.tif  (min=%.3f  mean=%.3f  max=%.3f)",
        float(np.nanmin(risk)),
        float(np.nanmean(risk)),
        float(np.nanmax(risk)),
    )
    return out_path
