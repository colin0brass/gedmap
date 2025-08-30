# gedmap

GEDCOM mapping and visualization

## Overview

**gedmap** is a tool for processing GEDCOM genealogy files, geolocating places, and exporting family events and relationships to KML format for visualization in Google Earth. It also generates summary statistics and visualizations.

## Features

- Parses GEDCOM files and extracts people, events, and places
- Checks the GEDCOM file and tries to fix if there are CONC/CONT level issues
  (as seen sometimes from Family Tree Maker export)
- Geocodes places using OpenStreetMap/Nominatim
- Caches geocoding results for efficiency (cache file stored in output folder)
- Exports birth, marriage, and death events as KML placemarks
- Draws family relationship lines in KML (e.g., parent-child)
- Generates summary statistics and visualizations (with pandas/seaborn/matplotlib)
- Command-line interface for batch processing
- Output files (KML, CSV summaries, cache) are placed in a configurable output folder

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
python gedmap.py <gedcom_file> [options]
```

### Options

- `--output_folder <folder>`: Folder to put output files (default: `./output`)
- `--geo_cache_filename <file>`: Path to geocode cache file (default: `geo_cache.csv` in output folder)
- `--default_country <country>`: Default country for geocoding (default: England)
- `--always-geocode`: Ignore cache and always geocode
- `--write_places_summary`: Save places summary as CSV
- `--write_people_summary`: Save people summary as CSV
- `--write_countries_summary`: Save countries summary and heatmap matrix
- `--write_all`: Save all summaries
- `--verbose`: Enable verbose output

### Example

```sh
python gedmap.py family.ged --output_folder results --write_all --verbose
```

## Output

- **KML file**: Visualize family events and relationships in Google Earth
- **CSV summaries**: Places, people, and countries summaries
- **Geocode cache**: Used for efficient repeated runs
- **Heatmap images**: Birth/death country heatmap matrixes

## Project Structure

- `gedmap.py` — Main entry point
- `gedcom.py` — GEDCOM parsing and data model
- `geocode.py` — Geocoding and location cache
- `location.py` — Location and LatLon classes
- `kml.py` — KML export logic
- `requirements.txt` — Python dependencies

## License

MIT License

## Author

Colin Osborne
