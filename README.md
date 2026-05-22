# Intelligent Flood Evacuation System

An intelligent geospatial analysis system that processes terrain and flood data to generate optimized evacuation routes and visualizations.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [System Components](#system-components)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Execution Guide](#execution-guide)
- [Output](#output)

## Overview

The Intelligent Flood Evacuation System is designed to analyze flood-prone areas and provide data-driven evacuation routes. It processes Digital Elevation Models (DEM), flood maps, road networks, and waterway data to:

1. Ingest and validate geospatial data
2. Analyze terrain characteristics (slope, risk assessment)
3. Classify road suitability for evacuation
4. Generate interactive evacuation maps
5. Serve real-time evacuation information via a web interface

## Project Structure

```
flood-evac-map/
├── config/                    # Configuration files
│   └── params.yaml           # System parameters and settings
├── data/                      # Data storage
│   ├── derived/              # Processed/derived data outputs
│   └── processed/            # Intermediate processing results
├── cache/                     # Caching layer for downloaded data
├── outputs/                   # Final output maps and visualizations
├── src/                       # Source code
│   ├── ingest/              # Data ingestion modules
│   ├── terrain/             # Terrain analysis modules
│   ├── classify/            # Road classification modules
│   ├── visualize/           # Map visualization modules
│   ├── route/               # Route optimization modules
│   └── web/                 # Web server and interface
├── tests/                     # Unit and integration tests
├── main.py                    # CLI entry point for batch processing
├── run_web.py                # Web server entry point
└── requirements.txt           # Python dependencies
```

## System Components

### 1. **Data Ingestion (`src/ingest/`)**
Handles loading and validation of geospatial data sources.

**Modules:**
- **`pipeline.py`**: Orchestrates the complete data ingestion workflow
- **`dem.py`**: Downloads and processes Digital Elevation Model (DEM) data
- **`flood.py`**: Ingests flood map data and rasterizes it to match DEM resolution
- **`network.py`**: Extracts road networks and waterways from OpenStreetMap

**Output:**
- DEM raster file
- Flood extent raster file
- Road network vector file
- Waterways vector file

### 2. **Terrain Analysis (`src/terrain/`)**
Performs geospatial analysis on terrain characteristics.

**Modules:**
- **`slope.py`**: Calculates slope gradient from DEM data using Sobel operators
- **`risk.py`**: Generates flood risk scores by combining:
  - Flood extent data
  - Elevation analysis
  - Slope characteristics
  - Proximity to flood zones

**Output:**
- Slope raster (gradient values)
- Risk score raster (0-1 normalized values)

### 3. **Road Classification (`src/classify/`)**
Evaluates and classifies roads based on evacuation suitability.

**Modules:**
- **`pipelines.py`**: Manages the classification workflow
- **`road.py`**: Analyzes road characteristics including:
  - Flood risk exposure
  - Slope constraints
  - Connectivity analysis
  - Elevation gain/loss along routes

**Output:**
- Classified road network with evacuation suitability scores

### 4. **Visualization (`src/visualize/`)**
Creates interactive maps for web and static display.

**Modules:**
- **`map.py`**: Generates Folium-based interactive web maps with:
  - Evacuation routes overlaid
  - Risk zones highlighted
  - Slope visualization
  - Road classification color-coding

**Output:**
- Interactive HTML map file (typically in `outputs/` directory)

### 5. **Web Server (`src/web/`)**
Provides real-time access to evacuation information.

**Modules:**
- **`app.py`**: FastAPI application serving:
  - RESTful API endpoints for route queries
  - Static map serving
  - Health checks and system status
- **`templates/`**: HTML/JavaScript frontend templates for the web interface

**Features:**
- Real-time route calculation
- Interactive map interface
- Mobile-responsive design
- API documentation via Swagger UI

## Prerequisites

- **Python 3.8+**
- **Conda** (recommended for geospatial dependencies) or **pip**
- **GDAL** (Geospatial Data Abstraction Library)
- **Git**
- Internet connection (for downloading geospatial data)

### Operating System Notes

- **Windows**: Recommended to use Miniforge/Miniconda for dependency installation
- **Linux/Mac**: Standard Python environments work well

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Younes-Lougnidi/Intelligent-flood-evacuation-system-.git
cd Intelligent-flood-evacuation-system-/flood-evac-map
```

### 2. Create Virtual Environment (Recommended)

**Using Conda:**
```bash
conda create -n flood-evac python=3.10
conda activate flood-evac
```

**Using venv:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Verify Installation

```bash
python -c "import rasterio, geopandas, folium, fastapi; print('All dependencies installed successfully')"
```

## Configuration

### Main Configuration File: `config/params.yaml`

Edit this file to customize system behavior:

```yaml
# Area of Interest (AOI) - Geographic boundaries
aoi:
  bounds:
    west: <longitude>
    south: <latitude>
    east: <longitude>
    north: <latitude>

# Data source paths
paths:
  dem: "data/dem.tif"
  flood: "data/flood.tif"
  roads: "data/roads.gpkg"
  outputs: "outputs/"

# Terrain analysis parameters
terrain:
  slope_method: "sobel"
  risk_threshold: 0.5
  
# Road classification parameters
classification:
  min_elevation_gain: 100
  max_slope_grade: 15
  risk_weighting: 0.6

# Web server settings
server:
  host: "0.0.0.0"
  port: 8000
```

**Key Parameters:**
- `bounds`: Define your area of interest (supports any EPSG:4326 coordinates)
- `dem`: Path to Digital Elevation Model file
- `flood`: Path to flood map GeoTIFF
- `risk_threshold`: Minimum risk score to flag areas as high-risk
- `max_slope_grade`: Maximum slope percentage for safe evacuation routes

## Execution Guide

### Option 1: Batch Processing (Full Pipeline)

Run the complete analysis pipeline from start to finish:

```bash
python main.py
```

**This will execute in sequence:**
1. ✓ Data Ingestion - Download and process DEM, flood data, road networks
2. ✓ Terrain Analysis - Calculate slope and risk scores
3. ✓ Road Classification - Evaluate evacuation route suitability
4. ✓ Visualization - Generate interactive evacuation map

**Expected Output:**
```
============================================================
Intelligent Evacuation System - data ingestion
============================================================
14:32:15  Data ingestion starting...
14:32:45  -- Ingestion summary ----------------------------------------
14:32:45    AOI bounds   W=-0.1234  S=51.4567  E=0.1234  N=51.6789
14:32:45    DEM          data/dem.tif
14:32:45    Flood        data/flood.tif
14:32:45    Roads        data/roads.gpkg
14:32:45  ============================================================
...
[Process continues through all 4 steps]
```

### Option 2: Web Server (Interactive Access)

Start the web application for real-time access:

```bash
python run_web.py
```

**Output:**
```
============================================================
Intelligent Evacuation System - Web Server
Open http://127.0.0.1:8000 in your browser
From your phone (same Wi-Fi): http://<YOUR-PC-IP>:8000
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Access Points:**
- **Local Machine**: http://127.0.0.1:8000
- **Mobile (same network)**: http://[YOUR-PC-IP]:8000 (e.g., http://192.168.1.100:8000)
- **API Documentation**: http://127.0.0.1:8000/docs
- **Alternative API Docs**: http://127.0.0.1:8000/redoc

### Option 3: Individual Module Execution

Run specific components independently:

**Generate Only Slope Analysis:**
```python
from src.terrain.slope import compute
slope_path = compute(
    dem_path="data/dem.tif",
    output_dir="data/derived/processed"
)
```

**Generate Only Risk Assessment:**
```python
from src.terrain.risk import compute
risk_path = compute(
    dem_path="data/dem.tif",
    slope_path="data/derived/processed/slope.tif",
    flood_path="data/flood.tif",
    output_dir="data/derived/processed"
)
```

**Classify Roads:**
```python
from src.classify.pipelines import run
classify_result = run("config/params.yaml")
```

**Create Visualization Map:**
```python
from src.visualize.map import create_evacuation_map
map_path = create_evacuation_map(
    roads_path="data/roads_classified.gpkg",
    output_dir="outputs"
)
```

## Output

### Generated Files

After execution, the system produces:

**Location:** `outputs/` directory

| File | Type | Description |
|------|------|-------------|
| `evacuation_map.html` | Interactive Map | Folium-based web map with evacuation routes |
| `risk_score.tif` | Raster | Risk assessment heatmap (0-1 scale) |
| `slope.tif` | Raster | Slope gradient visualization |
| `roads_classified.gpkg` | Vector | Road network with suitability scores |

### Map Features

The generated evacuation map includes:

- **Road Classifications**: Color-coded by evacuation suitability
  - 🟢 Green: Highly suitable evacuation routes
  - 🟡 Yellow: Moderate suitability
  - 🔴 Red: High-risk zones

- **Risk Visualization**: Heat map overlay showing flood risk areas
- **Terrain Data**: Slope and elevation contours
- **Interactive Controls**: Zoom, pan, layer toggling
- **Legend**: Full documentation of visual elements

### Web Server Output

When running `run_web.py`, the server provides:

- **Interactive Map**: Real-time evacuation route visualization
- **REST API**: Endpoints for route calculation and data queries
- **API Explorer**: Swagger UI for testing endpoints
- **Mobile Access**: Responsive design for smartphones/tablets

## Database and Caching

### Cache Directory (`cache/`)
- Stores downloaded geospatial data to avoid re-downloading
- Reduces processing time on subsequent runs
- Can be manually cleared to force data re-download

### Data Directory (`data/`)
- **`derived/`**: Contains terrain analysis outputs
- **`processed/`**: Intermediate processing results
- Safe to delete between runs (will be regenerated)

---

**Project Owner:** Younes-Lougnidi  
**Repository:** [Intelligent-flood-evacuation-system-](https://github.com/Younes-Lougnidi/Intelligent-flood-evacuation-system-)
