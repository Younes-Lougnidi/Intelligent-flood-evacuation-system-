"""
Road classification.

Samples the continuous risk_score.tif (0-1) under each road segment
and labels every segment as SAFE / MODERATE / DANGEROUS.

Thresholds (tunable in config/params.yaml):
    safe_below      : 0.35
    danger_above    : 0.60
"""

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

log = logging.getLogger(__name__)

# Default thresholds — overridden by params.yaml
_SAFE_BELOW   = 0.35
_DANGER_ABOVE = 0.60


def _sample_risk_along_line(geom, risk_arr, transform, n_points=20):
    """
    Interpolates n_points evenly along a LineString and
    returns the mean + max risk value sampled from the raster.
    """
    coords = [
        geom.interpolate(i / n_points, normalized=True)
        for i in range(n_points + 1)
    ]
    values = []
    for pt in coords:
        col, row = ~transform * (pt.x, pt.y)
        r, c = int(row), int(col)
        if 0 <= r < risk_arr.shape[0] and 0 <= c < risk_arr.shape[1]:
            v = risk_arr[r, c]
            if not np.isnan(v):
                values.append(float(v))
    if not values:
        return np.nan, np.nan
    return float(np.mean(values)), float(np.max(values))


def classify(
    roads_path: Path,
    risk_path: Path,
    output_dir: Path,
    safe_below: float   = _SAFE_BELOW,
    danger_above: float = _DANGER_ABOVE,
) -> Path:
    """
    Tags each road segment with:
        risk_mean  — average risk score along the segment
        risk_max   — worst-case risk along the segment
        status     — SAFE / MODERATE / DANGEROUS
        color      — hex colour for map rendering

    Saves roads_classified.geojson and returns its path.
    """
    roads_path = Path(roads_path)
    risk_path  = Path(risk_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "roads_classified.geojson"

    if out_path.exists():
        log.info("CLASSIFY | cache hit -> %s", out_path)
        return out_path

    # Load risk raster
    with rasterio.open(risk_path) as src:
        risk_arr  = src.read(1).astype("float32")
        risk_crs  = src.crs
        risk_transform = src.transform

    # Load roads and reproject to risk raster CRS
    roads = gpd.read_file(roads_path)
    if roads.crs != risk_crs:
        roads = roads.to_crs(risk_crs)

    log.info("CLASSIFY | scoring %d road segments ...", len(roads))

    means, maxs, statuses, colors = [], [], [], []

    for geom in roads.geometry:
        if geom is None or geom.is_empty:
            means.append(np.nan); maxs.append(np.nan)
            statuses.append("UNKNOWN"); colors.append("#888888")
            continue

        mean_v, max_v = _sample_risk_along_line(geom, risk_arr, risk_transform)

        # Use max to be conservative (worst point on the road)
        score = max_v if not np.isnan(max_v) else mean_v

        if np.isnan(score):
            status, color = "UNKNOWN", "#888888"
        elif score < safe_below:
            status, color = "SAFE",      "#2ecc71"   # green
        elif score > danger_above:
            status, color = "DANGEROUS", "#e74c3c"   # red
        else:
            status, color = "MODERATE",  "#f39c12"   # orange

        means.append(round(mean_v, 4) if not np.isnan(mean_v) else None)
        maxs.append(round(max_v,  4) if not np.isnan(max_v)  else None)
        statuses.append(status)
        colors.append(color)

    roads["risk_mean"] = means
    roads["risk_max"]  = maxs
    roads["status"]    = statuses
    roads["color"]     = colors

    roads.to_file(out_path, driver="GeoJSON")

    counts = roads["status"].value_counts()
    log.info("CLASSIFY | SAFE=%d  MODERATE=%d  DANGEROUS=%d  UNKNOWN=%d",
             counts.get("SAFE", 0),
             counts.get("MODERATE", 0),
             counts.get("DANGEROUS", 0),
             counts.get("UNKNOWN", 0))
    log.info("CLASSIFY | saved -> %s", out_path)
    return out_path