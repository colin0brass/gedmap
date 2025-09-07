# gedmap

GEDCOM mapping and visualization

## Overview

**gedmap** is a tool for processing GEDCOM genealogy files, geolocating places, and exporting family events and relationships to KML format for visualization in Google Earth. It also generates summary statistics and visualizations.

This is mainly being used currently to expore workflow and implementation ideas for discussion with the author of this project:
- https://github.com/D-Jeffrey/gedcom-to-visualmap

Using some of the sample files from gedcom-to-visualmap as above

## Features

- Parses GEDCOM files and extracts people, events, and places
- Checks and corrects GEDCOM files for CONC/CONT level issues (common in Family Tree Maker exports)
- Geocodes places using OpenStreetMap/Nominatim
- Caches geocoding results for efficiency (cache file stored in output folder)
- Supports fuzzy address matching for improved cache hits and alternate spellings
- Uses alternative place/address names from supplemental files
- Exports birth, marriage, and death events as KML placemarks
- Draws family relationship lines in KML (e.g., parent-child)
- Generates summary statistics and visualizations (with pandas/seaborn/matplotlib)
- Command-line interface for batch processing
- Output files (KML, CSV summaries, cache) are placed in a configurable output folder

## Workflow Thoughts
- load geo config (countries, substitutions, etc)
- load global geo cache if applicable
- for each input file:
  - load gedcom file
  - load per file alt places if applicable
  - load per file geo cache if applicable
  - apply geo cache to place list, by alternate address if it exists, or normal addr
  - geolocate any remaining places that don't already have lat/lon
  - save updated geo cache
  - write KML output
  - write summaries if requested
- status and potential directions
  - trying "rapidfuzz" for fuzzy string matching for address resolution; not yet evaluated benefit
  - started adding "libpostal" for address parsing and normalization; not fully integrated yet
  - consider flagging locations that were manually vs automatically geocoded
  - consider adding a confidence score to geocoded locations

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
- `--always_geocode`: Ignore cache and always geocode
- `--write_places_summary`: Save places summary as CSV
- `--write_people_summary`: Save people summary as CSV
- `--write_countries_summary`: Save countries summary and heatmap matrix
- `--write_geocache_per_input_file`: Save geo-cache for each input file
- `--write_alt_place_summary`: Save alternative place names summary as CSV
- `--write_all`: Save all summaries
- `--verbose`: Enable verbose output
- `--include_canonical`: Include canonical address and parts in location data
- `--use_alt_places`: Use alternative place names from file (`<input_filename>_alt.csv`)

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
- `addressbook.py` — Fuzzy address book and matching logic
- `kml.py` — KML export logic
- `summary.py` — Summary statistics and CSV/image output
- `requirements.txt` — Python dependencies

## License

MIT License

## Author

Colin Osborne
