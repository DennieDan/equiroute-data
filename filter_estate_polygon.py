from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon


def filter_lta_layer_by_polygon(shapefile_path, output_path, polygon_coords):
    print(f"🔄 Processing {shapefile_path}...")

    # 1. Read the LTA Shapefile
    gdf = gpd.read_file(shapefile_path)

    # 2. Match Singapore's SVY21 coordinate system (EPSG:3414)
    # to standard GPS coordinates (WGS84 - EPSG:4326) if necessary
    if gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    # 3. Create a Shapely Polygon from the coordinate list
    # Crucial: Shapely expects (Longitude, Latitude) order
    poly_points = [(pt["lng"], pt["lat"]) for pt in polygon_coords]
    neighborhood_polygon = Polygon(poly_points)

    # 4. Filter data intersecting this polygon (Keeps intersecting features intact)
    filtered_gdf = gdf[gdf.geometry.intersects(neighborhood_polygon)]

    # 5. Export back as a clean, localized Shapefile bundle
    filtered_gdf.to_file(output_path)
    print(
        f"✅ Saved localized layer to {output_path} ({len(filtered_gdf)} features found)"
    )


# Get list of shapefiles in raw_data folder
# Loop all folders in GEOSPATIAL folder, get only the string right before underscore to be the shapefile names
GEOSPATIAL_DIR = Path("GEOSPATIAL")
CLEMENTI_MALL_DIR = Path("CLEMENTI_MALL")

# Your custom Clementi polygon coordinates
clementi_poly_coords = [
    {"lat": 1.3161273531516402, "lng": 103.76451730728151},
    {"lat": 1.3148616841675702, "lng": 103.76318693161012},
    {"lat": 1.3131026177342597, "lng": 103.76329421997072},
    {"lat": 1.3111719336386278, "lng": 103.76516103744507},
    {"lat": 1.3126092208293652, "lng": 103.7667489051819},
]


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

# Run the filter for your downloaded layers (Update names according to your extracted file filenames)
for folder in GEOSPATIAL_DIR.iterdir():
    if not folder.is_dir():
        continue
    shp_files = list(folder.glob("*.shp"))
    if not shp_files:
        print(f"⚠️ No .shp found in {folder.name}, skipping")
        continue
    layer = shp_files[0]  # Path to the .shp file
    filter_lta_layer_by_polygon(
        str(layer),
        str(CLEMENTI_MALL_DIR / f"{layer.stem}_Clementi_Mall.shp"),
        clementi_poly_coords,
    )

# Run the filter for your downloaded layers (Update names according to your extracted file filenames)
# filter_lta_layer("raw_data/Footpath.shp", "clementi_footpaths.shp", CLEMENTI_BBOX)
# filter_lta_layer("raw_data/KerbLine.shp", "clementi_kerblines.shp", CLEMENTI_BBOX)
