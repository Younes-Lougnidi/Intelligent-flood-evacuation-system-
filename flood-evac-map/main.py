"""
Intelligent Evacuation System - entry point.

Run from the project root:
    python main.py
"""

import logging
import os
import sys
import yaml
from pathlib import Path

# GDAL_DATA auto-detect (needed on Windows with miniforge when running
# outside a conda-activated shell)
if "GDAL_DATA" not in os.environ:
    # On Windows + miniforge, python.exe sits directly in the conda prefix dir.
    # Try both .parent (Windows) and .parent.parent (Unix envs) as fallbacks.
    for _candidate in [
        Path(sys.executable).parent / "Library" / "share" / "gdal",
        Path(sys.executable).parent.parent / "Library" / "share" / "gdal",
    ]:
        if _candidate.exists():
            os.environ["GDAL_DATA"] = str(_candidate)
            break

from src.ingest import pipeline as ingest_pipeline
from src.terrain.slope import compute as compute_slope
from src.terrain.risk  import compute as compute_risk
from src.classify import pipelines as classify_pipeline
from src.visualize.map import create_evacuation_map


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> None:
    _setup_logging()
    log = logging.getLogger(__name__)
    config_path = "config/params.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # ------------------------------------------------------------------ #
    #  Step 1 - Data ingestion                                            #
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("Intelligent Evacuation System - data ingestion")
    log.info("=" * 60)

    ingest = ingest_pipeline.run("config/params.yaml")

    log.info("")
    log.info("-- Ingestion summary " + "-" * 39)
    w, s, e, n = ingest["bounds"]
    log.info("  AOI bounds   W=%.4f  S=%.4f  E=%.4f  N=%.4f", w, s, e, n)
    log.info("  DEM          %s", ingest["dem"])
    log.info("  Flood        %s", ingest["flood"])
    log.info("  Roads        %s", ingest["roads"])
    log.info("  Waterways    %s", ingest["waterways"])
    log.info("-" * 60)

    # ------------------------------------------------------------------ #
    #  Step 2 - Terrain analysis                                          #
    # ------------------------------------------------------------------ #
    log.info("")
    log.info("=" * 60)
    log.info("Intelligent Evacuation System - terrain analysis")
    log.info("=" * 60)

    slope_path = compute_slope(
        dem_path   = ingest["dem"],
        output_dir = Path("data/derived/processed"),
    )

    risk_path = compute_risk(
        dem_path   = ingest["dem"],
        slope_path = slope_path,
        flood_path = ingest["flood"],
        output_dir = Path("data/derived/processed"),
    )

    log.info("")
    log.info("-- Terrain summary " + "-" * 41)
    log.info("  Slope        %s", slope_path)
    log.info("  Risk score   %s", risk_path)
    log.info("-" * 60)
    log.info("Terrain ready.  Next step: road classification (src/classify)")
    log.info("")
    # ------------------------------------------------------------------ #
    #  Step 3 - read classification
    # ------------------------------------------------------------------ #
    log.info("")
    log.info("=" * 60)
    log.info("Intelligent Evacuation System - road classification")
    log.info("=" * 60)

    classify = classify_pipeline.run("config/params.yaml")

    log.info("")
    log.info("-- Classification summary " + "-" * 34)
    log.info("  Roads classified  %s", classify["roads_classified"])
    log.info("-" * 60)
    log.info("Classification ready.  Next step: visualization (src/visualize)")
    # ------------------------------------------------------------------ #
    #  Step 4 - visualisation
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("Intelligent Evacuation System - visualization")
    log.info("=" * 60)

    # Ensure the output directory exists using your config paths
    viz_output_dir = Path(cfg["paths"]["outputs"])
    viz_output_dir.mkdir(parents=True, exist_ok=True)

    map_path = create_evacuation_map(
        roads_path = classify["roads_classified"],
        output_dir = viz_output_dir
    )

    log.info("Visualization ready at: %s", map_path)

if __name__ == "__main__":
    main()
