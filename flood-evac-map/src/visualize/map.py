import folium
import geopandas as gpd
from pathlib import Path

def create_evacuation_map(roads_path: Path, output_dir: Path) -> Path:
    """
    Generates an interactive HTML map showing road risk levels.
    """
    # Load classified roads and convert to WGS84 for web display
    roads = gpd.read_file(roads_path).to_crs(epsg=4326)
    
    # Initialize map at the center of your road network
    centroid = roads.geometry.unary_union.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=14, tiles="CartoDB positron")

    # Add road segments with popups for risk details
    for _, row in roads.iterrows():
        # Build the popup with the metrics you calculated (mean and max)
        max_r  = f"{row['risk_max']:.3f}"  if row['risk_max']  is not None else "N/A"
        mean_r = f"{row['risk_mean']:.3f}" if row['risk_mean'] is not None else "N/A"
        popup_content = (
            f"<b>Status:</b> {row['status']}<br>"
            f"<b>Max Risk:</b> {max_r}<br>"
            f"<b>Avg Risk:</b> {mean_r}"
        )
        
        folium.GeoJson(
            row['geometry'],
            style_function=lambda x, color=row['color']: {
                'color': color,
                'weight': 4,
                'opacity': 0.8
            }
        ).add_child(folium.Popup(popup_content)).add_to(m)

    out_path = output_dir / "evacuation_map.html"
    m.save(str(out_path))
    return out_path