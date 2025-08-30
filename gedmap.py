"""
gedmap.py - Main entry point for GEDCOM geolocation and KML export.

Processes GEDCOM files, geocodes places, writes summaries, and generates KML output.
"""

import os
import re
import csv
import argparse
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from geocode import Geocode
from gedcom import GeolocatedGedcom
from kml import KML_Life_Lines_Creator
from summary import (
    write_places_summary,
    write_people_summary,
    write_birth_death_countries_summary
)

# Constants
DEFAULT_COUNTRY = 'England'
GEO_CACHE_FILENAME = 'geo_cache.csv'

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
    parser.add_argument('--default_country', type=str, default=DEFAULT_COUNTRY,
        help='Default country for geocoding, or "none" to disable')
    parser.add_argument('--always-geocode', action='store_true',
        help='Always geocode, ignore cache')
    parser.add_argument('--geo_cache_filename', type=str, default=GEO_CACHE_FILENAME,
        help='Geo-location cache filename to use')
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

LINE_RE = re.compile(
    r'^(\d+)\s+(?:@[^@]+@\s+)?([A-Z0-9_]+)(.*)$'
)  # allow optional @xref@ before the tag

def fix_gedcom_conc_cont_levels(input_path: str) -> tuple[str, bool]:
    """
    Fixes GEDCOM files where CONC/CONT tags have incorrect levels.
    Returns the path to the fixed file and whether any changes were made.

    Args:
        input_path (str): Path to input GEDCOM file.

    Returns:
        tuple[str, bool]: (Path to fixed file, whether changes were made)
    """
    logger = logging.getLogger(__name__)
    temp_fd, temp_path = tempfile.mkstemp(suffix='.ged')
    os.close(temp_fd)

    cont_level = None
    changed = False

    try:
        with open(input_path, 'r', encoding='utf-8', newline='') as infile, \
             open(temp_path, 'w', encoding='utf-8', newline='') as outfile:
            for raw in infile:
                line = raw.rstrip('\r\n')
                m = LINE_RE.match(line)
                if not m:
                    outfile.write(raw)
                    continue

                level_s, tag, rest = m.groups()
                level = int(level_s)

                if tag in ('CONC', 'CONT'):
                    fixed_level = cont_level if cont_level is not None else level
                    outfile.write(f"{fixed_level} {tag}{rest}\n")
                    if fixed_level != level:
                        changed = True
                else:
                    cont_level = level + 1
                    outfile.write(raw)
    except IOError as e:
        logger.error(f"Failed to fix GEDCOM file {input_path}: {e}")
    return temp_path, changed

def write_kml(args: argparse.Namespace, gedcom: GeolocatedGedcom, output_file: str) -> None:
    """
    Generate a KML file from the geolocated GEDCOM data.
    Adds people and parent connections to the KML.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.
        gedcom (GeolocatedGedcom): Geolocated GEDCOM data.
        output_file (str): Output KML file path.
    """
    kml_life_lines_creator = KML_Life_Lines_Creator(output_file, gedcom, verbose=args.verbose)
    kml_life_lines_creator.add_people()
    kml_life_lines_creator.connect_parents()
    kml_life_lines_creator.save_kml()

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
    log_level = logging.INFO if args.verbose else logging.ERROR
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    logger = logging.getLogger(__name__)

    output_folder = Path(args.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    for input_file in args.input_files:
        # Support input_file as absolute or relative path
        input_path = Path(input_file)
        if not input_path.is_absolute():
            input_path = Path.cwd() / input_path
        base_file_name = input_path.stem

        logger.info(f'Reading GEDCOM file: {input_path}')
        fixed_gedcom_file, changed = fix_gedcom_conc_cont_levels(str(input_path))
        if not changed:
            gedcom_file = input_path
        else:
            # Save fixed GEDCOM file in the same directory as the input file
            gedcom_file = input_path.parent / f"{base_file_name}_fixed.ged"
            shutil.copyfile(fixed_gedcom_file, gedcom_file)
            logger.info(f"Copied fixed GEDCOM file to {gedcom_file}")

        logger.info('Geolocating all places...')
        geo_cache_path = input_path.parent / args.geo_cache_filename
        geocoder = Geocode(
            str(geo_cache_path),
            args.default_country,
            args.always_geocode
        )

        my_gedcom = GeolocatedGedcom(
            gedcom_file=str(gedcom_file),
            geocoder=geocoder,
            default_country=args.default_country,
            always_geocode=args.always_geocode,
            location_cache_file=str(geo_cache_path)
        )

        geocoder.save_address_cache()

        logger.info('Writing KML file...')
        output_file = output_folder / f"{base_file_name}.kml"
        write_kml(args, my_gedcom, str(output_file))

        if args.write_places_summary or args.write_all:
            output_file = output_folder / f"{base_file_name}_places.csv"
            logger.info(f"Writing places summary to {output_file}")
            write_places_summary(args, my_gedcom.full_place_dict, str(output_file))

        if args.write_people_summary or args.write_all:
            output_file = output_folder / f"{base_file_name}_people.csv"
            logger.info(f"Writing people summary to {output_file}")
            write_people_summary(args, my_gedcom.people, str(output_file))

        if args.write_countries_summary or args.write_all:
            output_file = output_folder / f"{base_file_name}_countries.csv"
            logger.info(f"Writing countries summary to {output_file}")
            write_birth_death_countries_summary(args, my_gedcom.people, str(output_file), base_file_name)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.getLogger(__name__).error(f"An error occurred: {e}", exc_info=True)