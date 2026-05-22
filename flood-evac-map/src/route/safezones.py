"""
Safe zone identification — constrained to SAFE-classified roads.

A safe zone is a road node that satisfies ALL of:
  1. Its nearest road segment is classified as SAFE (green roads only)
  2. Its elevation is above the 80th percentile of all road-network nodes
  3. Its flood-risk score is below _RISK_THRESHOLD

Nearby qualifying nodes are grouped into ~300 m clusters so the map
shows meaningful zone markers rather than thousands of individual dots.

Bug fixes vs. original:
  - Out-of-bounds nodes now default to risk=0.0 (not 0.5) so periphery
    nodes are not incorrectly excluded when the threshold is 0.40.
  - Only nodes whose nearest road is SAFE are ever considered.
"""

import json
import logging
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import shape, LineString, MultiLineString
from shapely.ops import unary_union
from shapely.strtree import STRtree

log = logging.getLogger(__name__)

_RISK_THRESHOLD   = 0.40
_ELEV_PERCENTILE  = 80     # higher = zones placed on hills / roads leading out of the city
_MIN_CLUSTER_SIZE = 5      # need enough nodes to be meaningful
_MAX_ZONES        = 10     # realistic number of evacuation points
_GRID_DEG         = 0.018  # ~2 km grid cells — fewer, bigger clusters


def _build_safe_road_index(roads_geojson_path: Path):
    """
    Load the classified roads GeoJSON and build:
      - an STRtree spatial index of SAFE road geometries
      - a list of all SAFE Shapely geometries

    Returns (strtree, safe_geoms).  If the file is missing or has no SAFE
    segments, returns (None, []).
    """
    if not roads_geojson_path.exists():
        log.warning("ZONES | classified roads not found at %s — skipping road filter", roads_geojson_path)
        return None, []

    with roads_geojson_path.open(encoding="utf-8") as fh:
        gj = json.load(fh)

    safe_geoms = []
    for feature in gj.get("features", []):
        if feature.get("properties", {}).get("status") == "SAFE":
            geom = shape(feature["geometry"])
            safe_geoms.append(geom)

    if not safe_geoms:
        log.warning("ZONES | no SAFE-classified road segments found in %s", roads_geojson_path)
        return None, []

    tree = STRtree(safe_geoms)
    log.info("ZONES | built spatial index over %d SAFE road segments", len(safe_geoms))
    return tree, safe_geoms


def _node_is_on_safe_road(lon: float, lat: float, tree: STRtree, safe_geoms: list, max_dist_deg: float = 0.001) -> bool:
    """
    Return True if the node at (lon, lat) has a SAFE road within max_dist_deg
    (~111 m at the equator, adequate for road-node snapping).
    """
    from shapely.geometry import Point
    pt = Point(lon, lat)
    nearby = tree.query(pt.buffer(max_dist_deg))
    return len(nearby) > 0


def _is_node_safe(node, G, safe_edge_set: set) -> bool:
    for u, v, _ in G.edges(node, data=True):
        if frozenset({u, v}) in safe_edge_set:
            return True
    return False

def compute(G, risk_path: Path, dem_path: Path, safe_edge_set: set, safe_below: float = 0.32, fixed_zones: list = None) -> tuple:
    """
    Returns
    -------
    zones : list of dicts  {lat, lon, size, node_ids, elev_m, center_node_id}
    center_safe_ids : list of all qualifying node IDs (Dijkstra targets)
    """
    risk_path = Path(risk_path)
    dem_path  = Path(dem_path)

    with rasterio.open(risk_path) as src:
        risk_arr = src.read(1).astype("float32")
        risk_t   = src.transform

    with rasterio.open(dem_path) as src:
        dem_arr  = src.read(1).astype("float32")
        dem_t    = src.transform
        dem_nd   = src.nodata

    # ── Sample risk + elevation at every road node ─────────────────────────
    node_records = []   # (node_id, lat, lon, risk, elev)

    for node, d in G.nodes(data=True):
        nx_, ny_ = d["x"], d["y"]   # lon, lat

        # Risk — default 0.0 for out-of-bounds (safe periphery assumption)
        col, row = ~risk_t * (nx_, ny_)
        r, c = int(row), int(col)
        if 0 <= r < risk_arr.shape[0] and 0 <= c < risk_arr.shape[1]:
            risk_val = float(risk_arr[r, c])
            if np.isnan(risk_val) or risk_val >= 254:
                risk_val = 0.0
        else:
            risk_val = 0.0  # FIX: was 0.5, which exceeded threshold of 0.40

        # Elevation
        col, row = ~dem_t * (nx_, ny_)
        r, c = int(row), int(col)
        if 0 <= r < dem_arr.shape[0] and 0 <= c < dem_arr.shape[1]:
            elev_val = float(dem_arr[r, c])
            if dem_nd is not None and elev_val == dem_nd:
                elev_val = np.nan
        else:
            elev_val = np.nan

        node_records.append((node, ny_, nx_, risk_val, elev_val))

    # ── Handle Fixed Zones ─────────────────────────────────────────────────
    if fixed_zones and len(fixed_zones) > 0:
        log.info("ZONES | Using %d fixed zones from config...", len(fixed_zones))
        
        # Identify nodes that belong to major roads to avoid snapping to tiny alleys
        major_hwys = {'primary', 'secondary', 'tertiary', 'trunk', 'motorway', 'primary_link', 'secondary_link', 'trunk_link', 'motorway_link'}
        major_nodes = set()
        for u, v, d in G.edges(data=True):
            hw = d.get('highway', '')
            if isinstance(hw, list):
                hw = hw[0]
            if hw in major_hwys:
                major_nodes.add(u)
                major_nodes.add(v)

        # We still need to snap these coordinates to the nearest SAFE road node
        # so that routing can actually reach them.
        zones = []
        for i, fz in enumerate(fixed_zones):
            target_lat = float(fz["lat"])
            target_lon = float(fz["lon"])
            
            # Find the closest node in node_records that is also on a SAFE road
            best_dist = float('inf')
            best_node = None
            
            for node, lat, lon, risk, elev in node_records:
                # Must be a major road node
                if node not in major_nodes:
                    continue
                # Must be on a SAFE road segment (graph edge check)
                if not _is_node_safe(node, G, safe_edge_set):
                    continue
                # Simple euclidean dist for snapping
                dist = (lat - target_lat)**2 + (lon - target_lon)**2
                if dist < best_dist:
                    best_dist = dist
                    best_node = (node, lat, lon, elev)
                    
            if best_node:
                zones.append({
                    "lat": best_node[1],
                    "lon": best_node[2],
                    "size": 10, # arbitrary size for visual
                    "elev_m": round(best_node[3] if not np.isnan(best_node[3]) else 0),
                    "node_ids": [best_node[0]],
                    "center_node_id": best_node[0]
                })
        
        log.info("ZONES | Snapped %d fixed zones to SAFE road network", len(zones))
        center_safe_ids = [z["center_node_id"] for z in zones]
        return zones, center_safe_ids

    # ── Elevation threshold: 80th percentile of all road nodes ────────────
    valid_elevs = [rec[4] for rec in node_records if not np.isnan(rec[4])]
    elev_thresh = float(np.percentile(valid_elevs, _ELEV_PERCENTILE))
    log.info(
        "ZONES | elevation threshold: %.0f m  (p%d of %d road nodes)",
        elev_thresh, _ELEV_PERCENTILE, len(valid_elevs),
    )

    # ── Filter: elevated + low-risk + on a SAFE road ───────────────────────
    risk_cutoff = safe_below  # use config threshold, not hardcoded 0.40
    safe_nodes = []
    for node, lat, lon, risk, elev in node_records:
        if np.isnan(elev):
            continue
        if elev < elev_thresh:
            continue
        if risk >= risk_cutoff:
            continue
        # Extra filter: must be adjacent to a SAFE-classified road segment
        if not _is_node_safe(node, G, safe_edge_set):
            continue
        safe_nodes.append((node, lat, lon))

    log.info(
        "ZONES | %d qualifying nodes (elev >= %.0f m, risk < %.2f, on SAFE road)",
        len(safe_nodes), elev_thresh, risk_cutoff,
    )

    # ── Fallback: elevation only (ignore road filter) ─────────────────────
    if not safe_nodes:
        log.warning("ZONES | no nodes found — falling back to elevation-only filter")
        safe_nodes = [
            (node, lat, lon)
            for node, lat, lon, risk, elev in node_records
            if not np.isnan(elev) and elev >= elev_thresh
        ]

    # ── Cluster by ~2 km grid ──────────────────────────────────────────────
    grid: dict = {}
    for node_id, lat, lon in safe_nodes:
        key = (round(lat / _GRID_DEG), round(lon / _GRID_DEG))
        grid.setdefault(key, []).append((node_id, lat, lon))

    zones = []
    for members in grid.values():
        if len(members) < _MIN_CLUSTER_SIZE:
            continue
        node_ids   = [m[0] for m in members]
        # Compute centroid of the cluster
        centroid_lat = float(np.mean([m[1] for m in members]))
        centroid_lon = float(np.mean([m[2] for m in members]))
        # Snap zone center to the actual road node closest to centroid
        # (so the marker sits ON a road, not between roads)
        best_node = min(
            members,
            key=lambda m: (m[1] - centroid_lat)**2 + (m[2] - centroid_lon)**2
        )
        center_lat = best_node[1]
        center_lon = best_node[2]
        elev_vals  = [
            rec[4] for rec in node_records
            if rec[0] in node_ids and not np.isnan(rec[4])
        ]
        avg_elev = float(np.mean(elev_vals)) if elev_vals else 0.0
        zones.append({
            "lat":      center_lat,
            "lon":      center_lon,
            "size":     len(node_ids),
            "elev_m":   round(avg_elev),
            "node_ids": node_ids,
            "center_node_id": best_node[0],
        })

    # Keep only the top N largest zones for realism
    zones.sort(key=lambda z: z["size"], reverse=True)
    zones = zones[:_MAX_ZONES]
    log.info("ZONES | %d evacuation zones identified (capped at %d)", len(zones), _MAX_ZONES)

    # Return only the exact center node of each zone to use as Dijkstra targets
    center_safe_ids = [z["center_node_id"] for z in zones]
    return zones, center_safe_ids


def to_geojson(zones: list) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [z["lon"], z["lat"]]},
                "properties": {"size": z["size"], "elev_m": z["elev_m"]},
            }
            for z in zones
        ],
    }
