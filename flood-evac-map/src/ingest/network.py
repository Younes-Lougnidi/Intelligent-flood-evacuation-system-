"""
OSM road and waterway ingestion via osmnx.

Both datasets are fetched as a square around the AOI centre point and saved
as GeoPackage files (one file per layer).  A cache check prevents redundant
downloads on repeated runs.
"""

import logging
from pathlib import Path

import geopandas as gpd
import osmnx as ox

log = logging.getLogger(__name__)

# Suppress osmnx's own verbose logging
logging.getLogger("osmnx").setLevel(logging.WARNING)


def _dist_m(buffer_km: float) -> float:
    """Half-width of the square bounding box in metres (osmnx uses radius)."""
    return buffer_km * 1_000


def download_roads(
    center_lat: float,
    center_lon: float,
    buffer_km: float,
    output_dir: Path,
) -> Path:
    """
    Fetch the drivable road network from OpenStreetMap.
    Returns the path to roads.gpkg.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path   = output_dir / "roads.gpkg"
    graph_path = output_dir / "road_graph.graphml"

    if out_path.exists() and graph_path.exists():
        log.info("ROADS | cache hit -> %s", out_path)
        return out_path

    log.info(
        "ROADS | fetching OSM drive network  (centre=%.4f,%.4f  r=%.0f m)",
        center_lat, center_lon, _dist_m(buffer_km),
    )

    G = ox.graph_from_point(
        center_point=(center_lat, center_lon),
        dist=_dist_m(buffer_km),
        network_type="drive",
        retain_all=False,
    )

    if not out_path.exists():
        _, edges = ox.graph_to_gdfs(G)
        keep = [
            c for c in ["name", "highway", "maxspeed", "oneway", "length", "geometry"]
            if c in edges.columns
        ]
        edges[keep].to_file(out_path, driver="GPKG", layer="roads")
        log.info("ROADS | saved %d road segments -> %s", len(edges), out_path)

    if not graph_path.exists():
        ox.save_graphml(G, graph_path)
        log.info("ROADS | graph saved -> %s", graph_path)

    return out_path


def download_waterways(
    center_lat: float,
    center_lon: float,
    buffer_km: float,
    output_dir: Path,
) -> Path:
    """
    Fetch rivers, streams, and canals from OpenStreetMap.
    Returns the path to waterways.gpkg.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "waterways.gpkg"

    if out_path.exists():
        log.info("HYDRO | cache hit -> %s", out_path)
        return out_path

    log.info(
        "HYDRO | fetching OSM waterways  (centre=%.4f,%.4f  r=%.0f m)",
        center_lat, center_lon, _dist_m(buffer_km),
    )

    tags = {"waterway": ["river", "stream", "canal", "drain", "ditch"]}

    try:
        features = ox.features_from_point(
            center_point=(center_lat, center_lon),
            tags=tags,
            dist=_dist_m(buffer_km),
        )
    except Exception as exc:
        if "InsufficientResponse" in type(exc).__name__ or "empty" in str(exc).lower():
            log.warning("HYDRO | no waterways found in AOI - saving empty layer")
            empty = gpd.GeoDataFrame(columns=["waterway", "geometry"], crs="EPSG:4326")
            empty.to_file(out_path, driver="GPKG", layer="waterways")
            return out_path
        raise

    # Keep only LineString / MultiLineString features (not polygons / points)
    features = features[
        features.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ].copy()

    keep = [c for c in ["name", "waterway", "geometry"] if c in features.columns]
    features[keep].to_file(out_path, driver="GPKG", layer="waterways")

    log.info("HYDRO | saved %d waterway segments -> %s", len(features), out_path)
    return out_path
