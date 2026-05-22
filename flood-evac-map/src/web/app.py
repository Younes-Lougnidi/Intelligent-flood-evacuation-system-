"""
FastAPI web application — Intelligent Evacuation System.

Run from the project root:
    python run_web.py

Changes vs. original
---------------------
- find_route() is CPU-bound; now runs in a thread pool (run_in_threadpool)
  so it never blocks the async event loop.
- Classified roads are pre-loaded at startup; SAFE edges are extracted to
  build a safe_edge_set for the router.
- Safe zones are computed only from SAFE-road nodes (roads_geojson_path
  passed to compute()).
- /api/config  — returns AOI centre so the frontend can position the map.
- /api/stats   — returns road segment counts by status.
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.route.router    import find_route, load_graph
from src.route.safezones import compute as compute_safe_zones, to_geojson

log = logging.getLogger(__name__)

_CONFIG_PATH   = Path("config/params.yaml")
_GRAPH_PATH    = Path("data/raw/roads/road_graph.graphml")
_RISK_PATH     = Path("data/derived/processed/risk_score.tif")
_DEM_PATH      = Path("data/raw/dem/dem_clipped.tif")
_ROADS_PATH    = Path("outputs/roads_classified.geojson")
_TEMPLATE_PATH = Path("src/web/templates/index.html")

_state: dict = {}


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open() as fh:
            return yaml.safe_load(fh)
    return {}


def _build_safe_edge_set(G, risk_path: Path, cfg: dict) -> set:
    """
    Classify each graph edge by sampling the risk raster at its endpoint
    nodes.  An edge is SAFE if the max risk at either endpoint falls below
    the ``safe_below`` threshold from config.

    This is more reliable than trying to match osmid keys between the
    GeoJSON and the graph — those keys are often stripped during export.
    """
    import numpy as np
    import rasterio

    safe_below = cfg.get("classify", {}).get("safe_below", 0.35)

    if not risk_path.exists():
        log.warning("SAFE-EDGES | risk raster not found at %s", risk_path)
        return set()

    with rasterio.open(risk_path) as src:
        risk_arr = src.read(1).astype("float32")
        transform = src.transform

    safe_set: set = set()
    for u, v in G.edges():
        risks = []
        for node in (u, v):
            nx_, ny_ = G.nodes[node]["x"], G.nodes[node]["y"]
            col, row = ~transform * (nx_, ny_)
            r, c = int(row), int(col)
            if 0 <= r < risk_arr.shape[0] and 0 <= c < risk_arr.shape[1]:
                val = float(risk_arr[r, c])
                if not np.isnan(val) and val < 254:
                    risks.append(val)
        if risks and max(risks) < safe_below:
            safe_set.add(frozenset({u, v}))

    log.info("SAFE-EDGES | %d / %d edges classified as SAFE", len(safe_set), G.number_of_edges())
    return safe_set


def _count_road_stats(roads_geojson: dict) -> dict:
    counts = {"SAFE": 0, "MODERATE": 0, "DANGEROUS": 0, "UNKNOWN": 0}
    for feat in roads_geojson.get("features", []):
        status = feat.get("properties", {}).get("status", "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("WEB | loading graph…")
    cfg = _load_config()
    try:
        G = load_graph(_GRAPH_PATH)

        # Load classified roads
        if _ROADS_PATH.exists():
            roads_json = json.loads(_ROADS_PATH.read_text(encoding="utf-8"))
            _state["roads_json"]  = roads_json
            _state["road_stats"]  = _count_road_stats(roads_json)

        # Build safe edge set by sampling risk raster at graph nodes
        _state["safe_edge_set"] = _build_safe_edge_set(G, _RISK_PATH, cfg)
        log.info(
            "WEB | %d SAFE edges in graph",
            len(_state["safe_edge_set"]),
        )

        if not _ROADS_PATH.exists():
            log.warning("WEB | %s not found — run main.py first", _ROADS_PATH)

        log.info("WEB | computing safe zones (SAFE roads only)…")
        zones, safe_ids = compute_safe_zones(
            G,
            _RISK_PATH,
            _DEM_PATH,
            safe_edge_set=_state["safe_edge_set"],
            safe_below=cfg.get("classify", {}).get("safe_below", 0.32),
            fixed_zones=cfg.get("fixed_zones")
        )

        _state["graph"]      = G
        _state["safe_ids"]   = safe_ids
        _state["zones"]      = zones
        _state["zones_json"] = to_geojson(zones)
        _state["config"]     = cfg

        log.info(
            "WEB | ready  (%d road nodes | %d safe zones | %d safe-route edges)",
            G.number_of_nodes(),
            len(zones),
            len(_state.get("safe_edge_set", [])),
        )

    except Exception as exc:
        log.error("WEB | startup error: %s", exc, exc_info=True)
        _state["error"] = str(exc)

    yield
    _state.clear()


app = FastAPI(title="Intelligent Evacuation System", lifespan=lifespan)


# ── Models ──────────────────────────────────────────────────────────────────

class LocationRequest(BaseModel):
    lat: float
    lon: float


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    if not _TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="UI template not found")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


@app.get("/api/config")
async def get_config():
    """Return AOI centre + buffer so the frontend can position the map."""
    cfg = _state.get("config", {})
    aoi = cfg.get("aoi", {})
    return JSONResponse({
        "center_lat": aoi.get("center_lat", 35.01791471664536),
        "center_lon": aoi.get("center_lon", -5.91161571975982),
        "buffer_km":  aoi.get("buffer_km",  15),
    })


@app.get("/api/stats")
async def get_stats():
    """Return road segment counts grouped by status."""
    if "road_stats" not in _state:
        return JSONResponse({"SAFE": 0, "MODERATE": 0, "DANGEROUS": 0, "UNKNOWN": 0})
    return JSONResponse(_state["road_stats"])


@app.get("/api/roads")
async def get_roads():
    if "roads_json" not in _state:
        raise HTTPException(
            status_code=404,
            detail="roads_classified.geojson not found. Run main.py first.",
        )
    return JSONResponse(_state["roads_json"])


@app.get("/api/safezones")
async def get_safezones():
    if "error" in _state:
        raise HTTPException(status_code=503, detail=_state["error"])
    return JSONResponse(_state.get("zones_json", {"type": "FeatureCollection", "features": []}))


@app.post("/api/evacuate")
async def evacuate(location: LocationRequest):
    if "error" in _state:
        raise HTTPException(status_code=503, detail=_state["error"])
    if "graph" not in _state:
        raise HTTPException(status_code=503, detail="Graph not loaded yet")

    try:
        # run_in_threadpool prevents Dijkstra from blocking the event loop
        route = await run_in_threadpool(
            find_route,
            lat=location.lat,
            lon=location.lon,
            G=_state["graph"],
            safe_node_ids=_state["safe_ids"],
            safe_edge_set=_state.get("safe_edge_set"),
            zones=_state.get("zones"),
        )
        return JSONResponse(route)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
