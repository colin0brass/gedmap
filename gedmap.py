"""
gedmap.py - Main entry point for GEDCOM geolocation and KML export.

Processes GEDCOM files, geocodes places, writes summaries, and generates KML output.
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
    write_birth_death_countries_summary
)

# Constants
GEO_CACHE_FILENAME = 'geo_cache.csv'
ALT_PLACE_FILENAME_SUFFIX = '_alt.csv'

def get_arg_parser() -> argparse.ArgumentParser:
    """
    Create and return the argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
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
    parser.add_argument('--geo_cache_filename', type=str, default=GEO_CACHE_FILENAME,
        help='Geo-location cache filename to use')
    parser.add_argument('--use_alt_places', action='store_true',
        help=f'Use alternative place names from file (<input_filename>{ALT_PLACE_FILENAME_SUFFIX})')
    parser.add_argument('--write_places_summary', action='store_true',
        help='Save places summary as CSV')
    parser.add_argument('--write_people_summary', action='store_true',
        help='Save people summary as CSV')
    parser.add_argument('--write_countries_summary', action='store_true',
        help='Save countries summary and heatmap')
    parser.add_argument('--write_all', action='store_true',
        help='Save all summaries')
    parser.add_argument('--verbose', action='store_true',
        help='Enable verbose output')
    parser.add_argument('--output_folder', type=str, default='output',
        help='Folder to put output files (default: ./output)')
    return parser

def main() -> None:
    """
    Main entry point for the gedmap script.
    Parses arguments, processes GEDCOM files, geolocates places, writes summaries and KML output.
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

    output_folder = Path(args.output_folder).resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    for gedcom_file in args.input_files:
        # Support gedcom_file as absolute or relative path
        input_path = Path(gedcom_file)
        if not input_path.is_absolute():
            input_path = (Path.cwd() / input_path).resolve()
        base_file_name = input_path.stem

        logger.info(f'Processing GEDCOM file: {gedcom_file}')
        geo_cache_path = input_path.parent / args.geo_cache_filename
        alt_place_file_path = input_path.parent / f"{base_file_name}{ALT_PLACE_FILENAME_SUFFIX}"
        my_gedcom = GeolocatedGedcom(
            gedcom_file=input_path.resolve(),
            location_cache_file=geo_cache_path,
            default_country=args.default_country,
            always_geocode=args.always_geocode,
            use_alt_places=args.use_alt_places,
            alt_place_file_path=alt_place_file_path if args.use_alt_places else None
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
            write_places_summary(args, my_gedcom.full_place_dict, str(places_summary_file))

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

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.getLogger(__name__).error(f"An error occurred: {e}", exc_info=True)