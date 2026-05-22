"""
SRTM 1 arc-second DEM ingestion via AWS Elevation Tiles (Mapzen/Tilezen).

Tiles are 1x1-degree gzipped HGT files (~3-7 MB each compressed).
URL pattern:
  https://s3.amazonaws.com/elevation-tiles-prod/skadi/{NS}{lat:02d}/{NS}{lat:02d}{EW}{lon:03d}.hgt.gz

The GDAL SRTMHGT driver reads the decompressed .hgt files natively.
Each tile is decompressed and cached; subsequent runs hit the local cache.
"""

import gzip
import logging
import math
from pathlib import Path

import rasterio
import rasterio.windows
from rasterio.io import MemoryFile
from rasterio.merge import merge
import requests

log = logging.getLogger(__name__)

_BASE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"


def _tile_parts(lat_floor: int, lon_floor: int) -> tuple:
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    lat_str = f"{ns}{abs(lat_floor):02d}"
    lon_str = f"{ew}{abs(lon_floor):03d}"
    return lat_str, lon_str


def _get_hgt_path(lat_floor: int, lon_floor: int, cache_dir: Path) -> Path | None:
    """
    Return path to a decompressed .hgt tile, downloading and caching as needed.
    Returns None if the tile does not exist (ocean / no data).
    """
    lat_str, lon_str = _tile_parts(lat_floor, lon_floor)
    filename = f"{lat_str}{lon_str}.hgt"
    hgt_path = cache_dir / filename

    if hgt_path.exists():
        log.info("DEM  | cache hit: %s", filename)
        return hgt_path

    url = f"{_BASE_URL}/{lat_str}/{filename}.gz"
    log.info("DEM  | downloading tile: %s", filename)

    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code == 404:
            log.warning("DEM  | tile not found (likely ocean): %s", filename)
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("DEM  | download failed for %s: %s", filename, exc)
        return None

    raw_gz = resp.content
    try:
        raw_hgt = gzip.decompress(raw_gz)
    except Exception as exc:
        log.warning("DEM  | decompression failed for %s: %s", filename, exc)
        return None

    hgt_path.write_bytes(raw_hgt)
    log.info("DEM  | saved %s (%.1f MB)", filename, len(raw_hgt) / 1e6)
    return hgt_path


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
    Download SRTM tiles for `bounds` = (west, south, east, north) in EPSG:4326,
    merge if multiple tiles are needed, and return the clipped GeoTIFF path.
    """
    west, south, east, north = bounds
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "dem_clipped.tif"

    if out_path.exists():
        log.info("DEM  | cache hit: dem_clipped.tif")
        return out_path

    lat_floors = range(math.floor(south), math.ceil(north))
    lon_floors = range(math.floor(west), math.ceil(east))

    memfiles: list[MemoryFile] = []

    for lat_f in lat_floors:
        for lon_f in lon_floors:
            hgt_path = _get_hgt_path(lat_f, lon_f, output_dir)
            if hgt_path is None:
                continue

            try:
                with rasterio.open(hgt_path) as src:
                    raw_win = src.window(west, south, east, north)
                    win = _clamp_window(raw_win, src.width, src.height)

                    if win.width < 1 or win.height < 1:
                        log.debug("DEM  | no overlap — skipping %s", hgt_path.name)
                        continue

                    data = src.read(window=win)
                    transform = src.window_transform(win)
                    meta = src.meta.copy()
                    meta.update(
                        driver="GTiff",
                        height=data.shape[1],
                        width=data.shape[2],
                        transform=transform,
                    )

                mf = MemoryFile()
                with mf.open(**meta) as ds:
                    ds.write(data)
                memfiles.append(mf)

            except Exception as exc:
                log.warning("DEM  | could not read %s: %s", hgt_path.name, exc)

    if not memfiles:
        raise RuntimeError(
            f"No SRTM tiles returned data for bounds {bounds}. "
            "Check network access to s3.amazonaws.com/elevation-tiles-prod"
        )

    if len(memfiles) == 1:
        with memfiles[0].open() as ds:
            merged = ds.read()
            merged_transform = ds.transform
            merged_meta = ds.meta.copy()
    else:
        datasets = [mf.open() for mf in memfiles]
        try:
            merged, merged_transform = merge(datasets)
            merged_meta = datasets[0].meta.copy()
            merged_meta.update(
                height=merged.shape[1],
                width=merged.shape[2],
                transform=merged_transform,
            )
        finally:
            for ds in datasets:
                ds.close()

    for mf in memfiles:
        mf.close()

    merged_meta.update(driver="GTiff")
    with rasterio.open(out_path, "w", **merged_meta) as dst:
        dst.write(merged)

    log.info(
        "DEM  | saved dem_clipped.tif  (%d x %d px, res=%.1f m)",
        merged.shape[2],
        merged.shape[1],
        abs(merged_transform.a) * 111_320,
    )
    return out_path
