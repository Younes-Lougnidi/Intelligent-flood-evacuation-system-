"""
Evacuation route finder.

Finds the shortest path (by road distance in metres) from the user's
location to the nearest pre-computed safe zone node.

Strategy
--------
1. Build a *safe-only* subgraph using edges flagged as SAFE in the
   classified roads GeoJSON.  Dijkstra runs on this restricted graph so
   the route never crosses a MODERATE or DANGEROUS segment.
2. If no pure-safe path exists (e.g. the user is surrounded by flooded
   roads) the algorithm falls back to the full undirected graph and sets
   ``"safe_route": false`` in the response properties.
3. One-way street restrictions are ignored (undirected graph) to keep
   all evacuation options open.

Config
------
AOI coordinates are loaded from ``config/params.yaml`` so changing the
study area in the config is all that is required.
"""

import logging
from pathlib import Path

import networkx as nx
import osmnx as ox
import yaml

log = logging.getLogger(__name__)

_CONFIG_PATH = Path("config/params.yaml")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_aoi_config() -> tuple[float, float, float]:
    """Return (center_lat, center_lon, buffer_km) from params.yaml."""
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open() as fh:
            cfg = yaml.safe_load(fh)
        aoi = cfg.get("aoi", {})
        return (
            float(aoi.get("center_lat", 35.01791471664536)),
            float(aoi.get("center_lon", -5.91161571975982)),
            float(aoi.get("buffer_km",  15)),
        )
    # Hard-coded fallback (Tetouan, Morocco)
    log.warning("ROUTE | config/params.yaml not found — using built-in AOI defaults")
    return 35.01791471664536, -5.91161571975982, 15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_graph(graph_path: Path) -> nx.Graph:
    """
    Load the road graph and return its undirected version.
    Downloads from OSM if the GraphML file does not exist yet.
    """
    graph_path = Path(graph_path)
    center_lat, center_lon, buffer_km = _load_aoi_config()

    if graph_path.exists():
        log.info("ROUTE | loading graph from %s", graph_path)
        G = ox.load_graphml(graph_path)
    else:
        log.info("ROUTE | graph not found — downloading from OSM (one-time)…")
        G = ox.graph_from_point(
            center_point=(center_lat, center_lon),
            dist=buffer_km * 1_000,
            network_type="drive",
            retain_all=False,
        )
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(G, graph_path)
        log.info("ROUTE | saved -> %s", graph_path)

    G_und = G.to_undirected()
    log.info(
        "ROUTE | graph ready  (%d nodes, %d edges, undirected)",
        G_und.number_of_nodes(),
        G_und.number_of_edges(),
    )
    return G_und


def build_safe_subgraph(G: nx.Graph, safe_edge_set: set) -> nx.Graph:
    """
    Return a view of G that contains only edges present in *safe_edge_set*.

    ``safe_edge_set`` is a set of frozenset({u, v}) pairs (order-independent)
    built from the SAFE-classified GeoJSON in app.py.
    """
    safe_edges = [
        (u, v, k)
        for u, v, k in G.edges(keys=True)
        if frozenset({u, v}) in safe_edge_set
    ]
    return G.edge_subgraph(safe_edges).copy()


def find_route(
    lat: float,
    lon: float,
    G: nx.Graph,
    safe_node_ids: list,
    safe_edge_set: set | None = None,
    zones: list | None = None,
) -> dict:
    """
    Return a GeoJSON FeatureCollection with:
        origin      — Point at the user's clicked location
        route       — LineString of the shortest road path to the nearest safe zone
        destination — Point at the safe zone cluster centre

    Parameters
    ----------
    lat, lon       : user location in WGS-84
    G              : full undirected road graph
    safe_node_ids  : list of node IDs that qualify as safe-zone targets
    safe_edge_set  : set of frozenset({u,v}) for every SAFE-classified edge.
                     When provided, routing prefers SAFE-only paths.
    zones          : list of zone dicts from safezones.compute() — used to
                     extend the route line to the zone centre marker.
    """
    # ── Step 1: snap user to nearest road node ──────────────────────────────
    origin_node = ox.nearest_nodes(G, lon, lat)

    # ── Step 2: restrict to largest connected component ────────────────────
    components = list(nx.connected_components(G))
    largest    = max(components, key=len)
    if origin_node not in largest:
        origin_node = ox.nearest_nodes(G.subgraph(largest), lon, lat)

    safe_in_component = [n for n in safe_node_ids if n in largest]
    if not safe_in_component:
        raise RuntimeError("No safe zones reachable from this location.")

    # ── Step 3: try SAFE-only routing first ────────────────────────────────
    used_safe_graph = False
    reachable = {}
    if safe_edge_set:
        G_safe = build_safe_subgraph(G, safe_edge_set)
        safe_comps = list(nx.connected_components(G_safe)) if G_safe.number_of_nodes() > 0 else []
        safe_largest = max(safe_comps, key=len) if safe_comps else set()

        if origin_node in safe_largest:
            safe_in_safe_graph = [n for n in safe_in_component if n in safe_largest]
            if safe_in_safe_graph:
                lengths, paths = nx.single_source_dijkstra(
                    G_safe, origin_node, weight="length"
                )
                reachable = {
                    n: (lengths[n], paths[n])
                    for n in safe_in_safe_graph
                    if n in lengths
                }
                if reachable:
                    used_safe_graph = True
                    log.info("ROUTE | found pure-SAFE path to %d candidates", len(reachable))

    # ── Step 4: fallback to full graph if no safe-only path ────────────────
    if not used_safe_graph:
        log.warning("ROUTE | no pure-SAFE path — falling back to full road graph")
        lengths, paths = nx.single_source_dijkstra(
            G, origin_node, weight="length"
        )
        reachable = {
            n: (lengths[n], paths[n])
            for n in safe_in_component
            if n in lengths
        }

    if not reachable:
        raise RuntimeError(
            "Could not reach any safe zone. "
            "Try clicking closer to the road network."
        )

    # ── Step 5: pick nearest safe zone by road distance ────────────────────
    target     = min(reachable, key=lambda n: reachable[n][0])
    path_nodes = reachable[target][1]
    distance_m = reachable[target][0]

    # Build coords from actual edge geometries (follow road curves)
    coords = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        edge_data = G[u][v]
        # MultiGraph: pick the shortest edge key
        best_key = min(edge_data, key=lambda k: edge_data[k].get("length", float("inf")))
        geom = edge_data[best_key].get("geometry")
        if geom:
            pts = list(geom.coords)  # [(lon, lat), ...]
            # Check direction: geometry may be stored u→v or v→u
            u_coord = (G.nodes[u]["x"], G.nodes[u]["y"])
            d_start = (pts[0][0] - u_coord[0]) ** 2 + (pts[0][1] - u_coord[1]) ** 2
            d_end   = (pts[-1][0] - u_coord[0]) ** 2 + (pts[-1][1] - u_coord[1]) ** 2
            if d_end < d_start:
                pts = pts[::-1]
            # Skip first point if duplicate of previous segment's last point
            start = 1 if coords and coords[-1] == pts[0] else 0
            coords.extend(pts[start:])
        else:
            # No geometry stored — fall back to straight node-to-node
            if not coords:
                coords.append((G.nodes[u]["x"], G.nodes[u]["y"]))
            coords.append((G.nodes[v]["x"], G.nodes[v]["y"]))
    if not coords:
        coords = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in path_nodes]

    # ── Step 6: find the zone cluster this target belongs to ───────────────
    dest_lon, dest_lat = coords[-1]  # route endpoint (the target node)
    if zones:
        for z in zones:
            if target == z.get("center_node_id") or target in z["node_ids"]:
                dest_lon = z["lon"]
                dest_lat = z["lat"]
                break

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"type": "origin"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "type":        "route",
                    "distance_m":  round(distance_m),
                    "distance_km": round(distance_m / 1_000, 2),
                    "waypoints":   len(path_nodes),
                    "safe_route":  used_safe_graph,
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [dest_lon, dest_lat]},
                "properties": {"type": "destination"},
            },
        ],
    }

