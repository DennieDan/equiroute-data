from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


def filter_lta_layer(shapefile_path, output_path, bbox_coords):
    print(f"🔄 Processing {shapefile_path}...")

    # 1. Read the LTA Shapefile
    gdf = gpd.read_file(shapefile_path)

    # 2. Match Singapore's SVY21 coordinate system (EPSG:3414)
    # to standard GPS coordinates (WGS84 - EPSG:4326) if necessary
    if gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    # 3. Create a cropping bounding box around your neighborhood
    min_lon, min_lat, max_lon, max_lat = bbox_coords
    neighborhood_box = box(min_lon, min_lat, max_lon, max_lat)

    # 4. Filter data intersecting this box
    filtered_gdf = gdf[gdf.geometry.intersects(neighborhood_box)]

    # 5. Export back as a clean, localized Shapefile bundle
    filtered_gdf.to_file(output_path)
    print(
        f"✅ Saved localized layer to {output_path} ({len(filtered_gdf)} features found)"
    )


# Get list of shapefiles in raw_data folder
# Loop all folders in GEOSPATIAL folder, get only the string right before underscore to be the shapefile names
GEOSPATIAL_DIR = Path("GEOSPATIAL")
CLEMENTI_DIR = Path("CLEMENTI")
# Loop subfolders only (skip .zip files)
shapefile_names = [
    "PassengerPickupBay",
    "TrainStation",
    "RetainingWall",
    "PedestrainOverheadbridge",
    "BusStopLocation",
    "ControlBox",
    "LampPost",
    "RoadCrossing",
    "TrafficLight",
    "RoadSectionLine",
    "VehicleBridge",
    "SpeedRegulatingStrip",
    "TaxiStand",
    "CyclingPath",
    "StreetPaint",
    "KerbLine",
    "GuardRail",
    "LaneMarking",
    "WordMarking",
    "DetectorLoop",
    "ArrowMarking",
    "ERPGantry",
    "Railing",
    "ConvexMirror",
    "CoveredLinkWay",
    "Bollard",
    "Footpath",
    "ParkingStandardsZone",
    "RoadHump",
]

# --- CONFIGURATION FOR YOUR HDB ESTATE ---
# Example Bounding Box for Central Toa Payoh Area [Min Lon, Min Lat, Max Lon, Max Lat]
CLEMENTI_BBOX = [103.751106, 1.296920, 103.789859, 1.324078]

# Run the filter for your downloaded layers (Update names according to your extracted file filenames)
for folder in GEOSPATIAL_DIR.iterdir():
    if not folder.is_dir():
        continue
    shp_files = list(folder.glob("*.shp"))
    if not shp_files:
        print(f"⚠️ No .shp found in {folder.name}, skipping")
        continue
    layer = shp_files[0]  # Path to the .shp file
    filter_lta_layer(
        str(layer),
        str(CLEMENTI_DIR / f"{layer.stem}_Clementi.shp"),
        CLEMENTI_BBOX,
    )

# Run the filter for your downloaded layers (Update names according to your extracted file filenames)
# filter_lta_layer("raw_data/Footpath.shp", "clementi_footpaths.shp", CLEMENTI_BBOX)
# filter_lta_layer("raw_data/KerbLine.shp", "clementi_kerblines.shp", CLEMENTI_BBOX)
