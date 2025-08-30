# gedmap

GEDCOM mapping and visualization

## Overview

**gedmap** is a tool for processing GEDCOM genealogy files, geolocating places, and exporting family events and relationships to KML format for visualization in Google Earth. It also generates summary statistics and visualizations.

## Features

- Parses GEDCOM files and extracts people, events, and places
- Geocodes places using OpenStreetMap/Nominatim
- Caches geocoding results for efficiency
- Exports birth, marriage, and death events as KML placemarks
- Draws family relationship lines in KML (e.g., parent-child)
- Generates summary statistics and visualizations (with pandas/seaborn/matplotlib)
- Command-line interface for batch processing

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/gedmap.git
    cd gedmap
    ```

2. Install dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Usage

```sh
python gedmap.py <path_to_gedcom_file> <output_kml_file> [options]
```

### Options

- `--cache_file <file>`: Path to geocode cache file
- `--default_country <country>`: Default country for geocoding (default: England)
- `--always_geocode`: Ignore cache and always geocode
- `--verbose`: Enable verbose output
- `--location_cache_file <file>`: Location cache file
- `--use_hyperlinks`: Use hyperlinks in KML descriptions
- `--main_person_id <id>`: Main person to focus camera on

### Example

```sh
python gedmap.py family.ged family.kml --verbose --use_hyperlinks
```

## Output

- **KML file**: Visualize family events and relationships in Google Earth
- **Summary statistics**: Optionally, generate CSV or plots of event distributions

## Project Structure

- `gedmap.py` — Main entry point
- `gedcom.py` — GEDCOM parsing and data model
- `geocode.py` — Geocoding and location cache
- `lat_lon.py` — Latitude/longitude utilities
- `kml.py` — KML export logic
- `requirements.txt` — Python dependencies

## License

MIT License

## Author

Your Name
