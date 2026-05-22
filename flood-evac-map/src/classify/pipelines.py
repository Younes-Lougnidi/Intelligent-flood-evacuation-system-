import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


def run(config_path: str = "config/params.yaml") -> dict:
    cfg_file = Path(config_path)
    with cfg_file.open() as f:
        cfg = yaml.safe_load(f)

    # Resolve paths relative to the project root (parent of config/)
    base         = cfg_file.parent.parent
    processed_dir = base / cfg["paths"]["processed"]
    output_dir    = base / cfg["paths"]["outputs"]
    # Road network path comes from config, not hardcoded
    roads_path    = base / cfg["paths"]["raw_roads"] / "roads.gpkg"

    from src.classify.road import classify

    roads_out = classify(
        roads_path   = roads_path,
        risk_path    = processed_dir / "risk_score.tif",
        output_dir   = output_dir,
        safe_below   = cfg.get("classify", {}).get("safe_below",   0.35),
        danger_above = cfg.get("classify", {}).get("danger_above", 0.60),
    )

    return {"roads_classified": roads_out}