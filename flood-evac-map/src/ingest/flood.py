"""
JRC Global Surface Water (GSW) — occurrence layer ingestion.

Tiles are 10°×10° COGs on Google Cloud Storage.  Each pixel stores the
percentage of time (0–100) a location was covered by surface water between
1984 and 2021.  We read only the AOI window via HTTP range requests.

Tile naming uses the NW corner in 10° increments:
  occurrence_{lon_abs}{EW}_{lat_abs}{NS}v1_4_2021.tif
  e.g. centre at (-5.9°, 35°)  ->  10W_40N
"""

import logging
import math
from pathlib import Path

import rasterio
import rasterio.windows

log = logging.getLogger(__name__)

_GCS_BASE = (
    "https://storage.googleapis.com/global-surface-water"
    "/downloads2021/occurrence"
)


def _tile_key(center_lat: float, center_lon: float) -> str:
    lon_floor10 = math.floor(center_lon / 10) * 10
    lat_ceil10 = math.ceil(center_lat / 10) * 10

    ew = "E" if lon_floor10 >= 0 else "W"
    ns = "N" if lat_ceil10 >= 0 else "S"

    return f"{abs(lon_floor10):d}{ew}_{abs(lat_ceil10):d}{ns}"


def _clamp_window(
    window: rasterio.windows.Window,
    src_width: int,
    src_height: int,
) -> rasterio.windows.Window:
    col_off = max(0.0, window.col_off)
    row_off = max(0.0, window.row_off)
    col_end = min(float(src_width), window.col_off + window.width)
    row_end = min(float(src_height), window.row_off + window.height)
    return rasterio.windows.Window(
        col_off=col_off,
        row_off=row_off,
        width=max(0.0, col_end - col_off),
        height=max(0.0, row_end - row_off),
    )


def download(bounds: tuple, output_dir: Path) -> Path:
    """
    Download (or load from cache) the JRC GSW occurrence layer clipped to
    `bounds` = (west, south, east, north) in EPSG:4326.

    Returns the path to the clipped GeoTIFF.
    Pixel values: 0 = never water, 100 = always water, 255 = no data.
    """
    west, south, east, north = bounds
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "flood_occurrence_clipped.tif"

    if out_path.exists():
        log.info("FLOOD | cache hit -> %s", out_path)
        return out_path

    center_lat = (south + north) / 2
    center_lon = (west + east) / 2
    key = _tile_key(center_lat, center_lon)
    url = f"{_GCS_BASE}/occurrence_{key}v1_4_2021.tif"

    log.info("FLOOD | reading JRC GSW tile window: occurrence_%s", key)

    try:
        with rasterio.open(url) as src:
            raw_win = src.window(west, south, east, north)
            win = _clamp_window(raw_win, src.width, src.height)

            if win.width < 1 or win.height < 1:
                raise RuntimeError(
                    f"JRC tile {key} has no overlap with AOI {bounds}"
                )

            data = src.read(window=win)
            transform = src.window_transform(win)
            meta = src.meta.copy()

    except Exception as exc:
        raise RuntimeError(
            f"Failed to read JRC GSW tile '{key}' from GCS.\n"
            f"URL: {url}\nReason: {exc}"
        ) from exc

    meta.update(
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        transform=transform,
    )
    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(data)

    log.info(
        "FLOOD | saved %s  (%d x %d px)",
        out_path,
        data.shape[2],
        data.shape[1],
    )
    return out_path
