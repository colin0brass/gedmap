"""
gedmap.py - Main entry point for GEDCOM geolocation and KML export.

Processes GEDCOM files, geocodes places, writes summaries, and generates KML output.

Workflow:
    1. Parse command-line arguments for input files, output folder, and options.
    2. For each GEDCOM file:
        - Resolve file paths and output locations.
        - Parse and correct GEDCOM file structure if needed.
        - Geocode places using OpenStreetMap/Nominatim, with caching and fuzzy matching.
        - Optionally use alternative place/address files for improved geocoding.
        - Save updated geocoding cache.
        - Export events and relationships to KML for Google Earth.
        - Write summary CSVs for places, people, countries, and alternative addresses.
        - Generate birth/death country heatmaps and other visualizations.
    3. All output files are saved in the specified output folder.
"""

import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from geocode import Geocode
from gedcom import GeolocatedGedcom
from kml import KML_Life_Lines
from summary import (
    write_places_summary,
    write_people_summary,
    write_birth_death_countries_summary,
    write_geocache_summary,
    write_alt_places_summary
)

# Constants
GLOBAL_GEO_CACHE_FILENAME = 'geo_cache.csv'
FILE_ALT_PLACE_FILENAME_SUFFIX = '_alt.csv'
FILE_GEOCACHE_FILENAME_SUFFIX = '_cache.csv'
GEO_CONFIG_FILENAME = 'geo_config.yaml'

def get_arg_parser() -> argparse.ArgumentParser:
    """
    Create and return the argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: Configured argument parser.

    Options:
        input_files (str): One or more GEDCOM files to process.
        --default_country (str): Default country for geocoding.
        --always-geocode: Always geocode, ignore cache.
        --geo_cache_filename (str): Geo-location cache filename to use.
        --skip_file_alt_places: Ignore alternative place names for each input file (<input_filename>_alt.csv).
        --skip_file_geocache: Ignore geo-cache for each input file (<input_filename>_cache.csv).
        --write_places_summary: Save places summary as CSV.
        --write_people_summary: Save people summary as CSV.
        --write_countries_summary: Save countries summary and heatmap.
        --write_geocache_per_input_file: Save geo-cache for each input file.
        --write_alt_place_summary: Save alternative place names summary as CSV.
        --write_all: Save all summaries.
        --verbose: Enable verbose output.
        --output_folder (str): Folder to put output files.
        --include_canonical: Include canonical address and parts in location data.
    """
    parser = argparse.ArgumentParser(
        description='Convert GEDCOM to KML and lookup addresses',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input_files', type=str, nargs='+',
        help='One or more GEDCOM files to process')
    parser.add_argument('--default_country', type=str, default=None,
        help='Default country for geocoding, e.g. "England"')
    parser.add_argument('--always-geocode', action='store_true',
        help='Always geocode, ignore cache')
    parser.add_argument('--geo_cache_filename', type=str, default=GLOBAL_GEO_CACHE_FILENAME,
        help='Global geo-location cache filename to use')
    parser.add_argument('--skip_file_alt_places', action='store_true',
        help=f'Ignore alternative place names for each input file (<input_filename>{FILE_ALT_PLACE_FILENAME_SUFFIX})')
    parser.add_argument('--skip_file_geocache', action='store_true',
        help=f'Ignore geo-cache for each input file (<input_filename>{FILE_GEOCACHE_FILENAME_SUFFIX})')
    parser.add_argument('--write_places_summary', action='store_true',
        help='Save places summary as CSV')
    parser.add_argument('--write_people_summary', action='store_true',
        help='Save people summary as CSV')
    parser.add_argument('--write_countries_summary', action='store_true',
        help='Save countries summary and heatmap')
    parser.add_argument('--write_geocache_per_input_file', action='store_true',
        help='Save geo-cache for each input file')
    parser.add_argument('--write_alt_place_summary', action='store_true',
        help='Save alternative place names summary as CSV')
    parser.add_argument('--write_all', action='store_true',
        help='Save all summaries')
    parser.add_argument('--verbose', action='store_true',
        help='Enable verbose output')
    parser.add_argument('--output_folder', type=str, default='output',
        help='Folder to put output files (default: ./output)')
    parser.add_argument('--include_canonical', action='store_true',
        help='Include canonical address and parts in location data')
    return parser

def main() -> None:
    """
    Main entry point for the gedmap script.

    Parses arguments, processes GEDCOM files, geolocates places, writes summaries, and generates KML output.

    Workflow:
        - Parse CLI arguments.
        - For each input GEDCOM file:
            - Resolve paths and filenames.
            - Parse and correct GEDCOM file.
            - Geocode places and cache results.
            - Optionally use alternative place/address files.
            - Save updated cache.
            - Export events and relationships to KML.
            - Write summary CSVs and visualizations.
        - Save all outputs in the specified output folder.
    """
    parser = get_arg_parser()
    args = parser.parse_args()
    if not args.input_files:
        parser.error("At least one input file is required")

    # Configure logging before any logging calls
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    logger = logging.getLogger(__name__)

    script_dir = Path(__file__).parent.resolve()
    geo_config_path = script_dir / GEO_CONFIG_FILENAME

    output_folder = Path(args.output_folder).resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    for gedcom_file in args.input_files:
        # Support gedcom_file as absolute or relative path
        input_path = Path(gedcom_file)
        if not input_path.is_absolute():
            input_path = (Path.cwd() / input_path).resolve()
        base_file_name = input_path.stem

        logger.info(f'Processing GEDCOM file: {gedcom_file}')
        global_geo_cache_path = input_path.parent / args.geo_cache_filename
        alt_place_file_path = input_path.parent / f"{base_file_name}{FILE_ALT_PLACE_FILENAME_SUFFIX}"
        file_geo_cache_path = input_path.parent / f"{base_file_name}{FILE_GEOCACHE_FILENAME_SUFFIX}"
        my_gedcom = GeolocatedGedcom(
            gedcom_file=input_path.resolve(),
            location_cache_file=global_geo_cache_path,
            default_country=args.default_country,
            always_geocode=args.always_geocode,
            alt_place_file_path=alt_place_file_path if not args.skip_file_alt_places else None,
            geo_config_path=geo_config_path if geo_config_path.exists() else None,
            file_geo_cache_path=file_geo_cache_path if not args.skip_file_geocache else None,
            include_canonical= args.include_canonical
        )

        logger.info('Saving updated geo cache...')
        my_gedcom.save_location_cache()

        output_file = output_folder / f"{base_file_name}.kml"
        output_file = output_file.resolve()
        logger.info(f'Writing KML to {output_file}')
        kml_life_lines = KML_Life_Lines(gedcom=my_gedcom, kml_file=str(output_file),
                                        connect_parents=True, save=True)

        if args.write_places_summary or args.write_all:
            places_summary_file = output_folder / f"{base_file_name}_places.csv"
            places_summary_file = places_summary_file.resolve()
            logger.info(f"Writing places summary to {places_summary_file}")
            write_places_summary(args, my_gedcom.address_book, str(places_summary_file))

        if args.write_people_summary or args.write_all:
            people_summary_file = output_folder / f"{base_file_name}_people.csv"
            people_summary_file = people_summary_file.resolve()
            logger.info(f"Writing people summary to {people_summary_file}")
            write_people_summary(args, my_gedcom.people, str(people_summary_file))

        if args.write_countries_summary or args.write_all:
            countries_summary_file = output_folder / f"{base_file_name}_countries.csv"
            countries_summary_file = countries_summary_file.resolve()
            logger.info(f"Writing countries summary to {countries_summary_file}")
            write_birth_death_countries_summary(args, my_gedcom.people, str(countries_summary_file), base_file_name)

        if args.write_geocache_per_input_file or args.write_all:
            per_file_cache = output_folder / f"{base_file_name}{FILE_GEOCACHE_FILENAME_SUFFIX}"
            per_file_cache = per_file_cache.resolve()
            logger.info(f"Writing geo cache to {per_file_cache}")
            write_geocache_summary(my_gedcom.address_book, str(per_file_cache))

        if not args.skip_file_alt_places and (args.write_alt_place_summary or args.write_all):
            alt_places_summary_file = output_folder / f"{base_file_name}_alt_places.csv"
            alt_places_summary_file = alt_places_summary_file.resolve()
            logger.info(f"Writing alternative places summary to {alt_places_summary_file}")
            write_alt_places_summary(args, my_gedcom.address_book, str(alt_places_summary_file))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.getLogger(__name__).error(f"An error occurred: {e}", exc_info=True)