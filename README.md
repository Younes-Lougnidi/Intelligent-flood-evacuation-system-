# Intelligent Flood Evacuation System

A geospatial analysis system that processes terrain and flood data to generate optimized evacuation routes and interactive maps.

## Project Overview

### The Problem
Floods are among the most devastating natural disasters, affecting millions of people worldwide. When flood events occur, emergency responders and affected communities need immediate, accurate information to:
- Identify safe evacuation routes
- Prioritize high-risk areas for rescue operations
- Make data-driven decisions under time constraints

Traditional evacuation planning relies on static maps and historical data, which cannot adapt to real-time flood conditions or account for complex terrain analysis.

### Our Solution
This **Intelligent Flood Evacuation System** combines geospatial analysis, terrain modeling, and network optimization to create dynamic, data-driven evacuation guidance. The system:

1. **Analyzes Terrain**: Processes Digital Elevation Models (DEM) to understand slope, elevation, and natural barriers
2. **Models Flood Risk**: Combines historical flood data with terrain analysis to calculate dynamic risk scores
3. **Evaluates Infrastructure**: Assesses road networks for evacuation suitability based on safety, accessibility, and connectivity
4. **Generates Routes**: Creates optimized evacuation routes that balance speed, safety, and accessibility
5. **Visualizes Results**: Provides interactive maps for emergency responders, planners, and the public

### Key Features
- 🌍 **Geospatial Intelligence**: Uses global open data sources (Copernicus, JRC) for terrain and flood analysis
- 🗺️ **Interactive Mapping**: Real-time, web-based visualization of evacuation routes and risk zones
- 🚗 **Road Classification**: Intelligent scoring system that identifies safe, passable evacuation corridors
- 📊 **Risk Assessment**: Multi-factor analysis combining elevation, slope, and flood probability
- ⚡ **Real-Time Web Server**: FastAPI backend for instant evacuation recommendations
- 🔧 **Modular Design**: Run as batch analysis or deploy as a live service

### Use Cases
- **Emergency Management**: Plan and execute coordinated evacuations during flood alerts
- **Urban Planning**: Identify vulnerable infrastructure and plan improvements
- **Climate Adaptation**: Assess long-term flood risks and resilience strategies
- **Disaster Response**: Provide real-time routing for rescue operations and resource deployment
- **Public Awareness**: Enable communities to understand local flood risks

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the System

**Full Analysis:**
```bash
python main.py
```

**Web Server (Interactive Map):**
```bash
python run_web.py
```
Then open: http://127.0.0.1:8000

## Project Structure

```
flood-evac-map/
├── config/
│   └── params.yaml           # Configuration settings
├── data/                      # Data storage
│   ├── raw/                  # Raw geospatial data
│   └── derived/              # Processed outputs
├── src/                       # Source code
│   ├── ingest/              # Data loading
│   ├── terrain/             # Slope & risk analysis
│   ├── classify/            # Road classification
│   ├── visualize/           # Map generation
│   └── web/                 # Web server
├── main.py                    # Batch processing entry point
├── run_web.py                # Web server entry point
└── requirements.txt           # Dependencies
```

## System Components

### Step 1: Data Ingestion (`src/ingest/`)
Downloads and processes geospatial data:
- Digital Elevation Model (DEM)
- Flood maps
- Road networks
- Waterways

**Files:**
- `pipeline.py` - Orchestrates ingestion
- `dem.py` - Processes elevation data
- `flood.py` - Processes flood extent data
- `network.py` - Extracts roads and waterways

### Step 2: Terrain Analysis (`src/terrain/`)
Analyzes terrain characteristics:
- `slope.py` - Calculates slope gradients
- `risk.py` - Generates flood risk scores (combines DEM, slope, flood data)

### Step 3: Road Classification (`src/classify/`)
Evaluates road suitability for evacuation:
- `road.py` - Analyzes road characteristics
- `pipelines.py` - Manages workflow

**Output:** Roads scored by evacuation suitability

### Step 4: Visualization (`src/visualize/`)
Creates interactive maps:
- `map.py` - Generates Folium-based HTML maps with evacuation routes, risk zones, and terrain

### Step 5: Web Server (`src/web/`)
Serves real-time evacuation information:
- `app.py` - FastAPI server with REST API
- `templates/` - Web interface

## Configuration

Edit `config/params.yaml` to customize:

```yaml
# Study area center point and radius
aoi:
  center_lat: 35.01791471664536
  center_lon: -5.91161571975982
  buffer_km: 15              # Area radius in kilometers

# Data sources
dem:
  source: copernicus_glo30   # 30m elevation data
flood:
  source: jrc_gsw            # Global surface water data
  layer: occurrence          # Water presence (0-100%)

# File paths
paths:
  raw_dem:      data/raw/dem
  raw_flood:    data/raw/historical
  raw_hydro:    data/raw/hydro
  raw_roads:    data/raw/roads
  processed:    data/derived/processed
  outputs:      outputs

# Road classification thresholds
classify:
  safe_below:   0.33        # Risk score < 0.33 = safe
  danger_above: 0.35        # Risk score > 0.35 = danger

# Evacuation zone locations (optional)
fixed_zones:
  - lat: 35.024
    lon: -5.903
  - lat: 35.012
    lon: -5.930
  # Add more zones as needed
```

## Execution Guide

### Option 1: Full Pipeline

```bash
python main.py
```

Runs all 4 steps sequentially:
1. ✓ Data ingestion
2. ✓ Terrain analysis (slope & risk)
3. ✓ Road classification
4. ✓ Map generation

**Output:** Interactive map in `outputs/evacuation_map.html`

### Option 2: Web Server

```bash
python run_web.py
```

**Access:**
- Local: http://127.0.0.1:8000
- Mobile (same network): http://[YOUR-PC-IP]:8000
- API docs: http://127.0.0.1:8000/docs

### Option 3: Run Individual Modules

```python
# Generate slope analysis
from src.terrain.slope import compute
slope_path = compute(dem_path="data/dem.tif", output_dir="data/derived/processed")

# Generate risk assessment
from src.terrain.risk import compute
risk_path = compute(
    dem_path="data/dem.tif",
    slope_path=slope_path,
    flood_path="data/flood.tif",
    output_dir="data/derived/processed"
)

# Classify roads
from src.classify.pipelines import run
roads = run("config/params.yaml")

# Create map
from src.visualize.map import create_evacuation_map
map_file = create_evacuation_map(roads_path="data/roads_classified.gpkg", output_dir="outputs")
```

## Output Files

Generated in `outputs/` directory:

| File | Description |
|------|-------------|
| `evacuation_map.html` | Interactive web map with evacuation routes |
| `risk_score.tif` | Risk assessment heatmap (0-1 scale) |
| `slope.tif` | Slope gradient visualization |
| `roads_classified.gpkg` | Road network with suitability scores |

### Map Legend

- 🟢 **Green** - Highly suitable evacuation routes
- 🟡 **Yellow** - Moderate suitability
- 🔴 **Red** - High-risk zones

## Requirements

- Python 3.8+
- See `requirements.txt` for all dependencies (rasterio, geopandas, folium, fastapi, etc.)

## Data Directories

- **`cache/`** - Cached downloaded data (safe to delete)
- **`data/raw/`** - Raw geospatial input data
- **`data/derived/`** - Processed analysis outputs
- **`outputs/`** - Final maps and visualizations

---

**Repository:** [Intelligent-flood-evacuation-system-](https://github.com/Younes-Lougnidi/Intelligent-flood-evacuation-system-)
