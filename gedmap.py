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

# Constants
DEFAULT_COUNTRY = 'England'
GEO_CACHE_FILENAME = 'geo_cache.csv'

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

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

def write_places_summary(args: argparse.Namespace, full_geolocation_dict: Dict[str, Any], output_file: str) -> None:
    """
    Write a summary of all geolocated places to a CSV file.
    Each row contains: count, latitude, longitude, found_country, has_date, place, country, continent, region.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.
        full_geolocation_dict (dict): Dictionary of geolocated places.
        output_file (str): Output CSV file path.
    """
    try:
        with open(output_file, 'w', newline='') as csvfile:
            csv_header = [
                'count', 'latitude', 'longitude', 'found_country', 'has_date',
                'place', 'country', 'continent'
            ]
            csv_writer = csv.writer(csvfile, dialect='excel')
            csv_writer.writerow(csv_header)
            for place, data in full_geolocation_dict.items():
                location = data.get('location', None)
                latitude = getattr(location.lat_lon, 'lat', '') if location and getattr(location, 'lat_lon', None) else ''
                longitude = getattr(location.lat_lon, 'lon', '') if location and getattr(location, 'lat_lon', None) else ''
                found_country = getattr(location, 'found_country', '') if location else ''
                has_date = data.get('has_date', False)
                country = getattr(location, 'country', '') if location else ''
                continent = getattr(location, 'continent', '') if location else ''
                r = [
                    data['count'], latitude, longitude, found_country, has_date,
                    place, country, continent
                ]
                csv_writer.writerow(r)
    except IOError as e:
        logger.error(f"Failed to write places summary to {output_file}: {e}")

def write_people_summary(args: argparse.Namespace, people: Dict[str, Any], output_file: str) -> None:
    """
    Write a summary of all people to a CSV file.
    Each row contains: ID, Name, birth/death place/date/country/continent.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.
        people (dict): Dictionary of people.
        output_file (str): Output CSV file path.
    """
    people_summary = []
    for person_id, person in people.items():
        birth_place = person.birth.place if person.birth else ''
        birth_continent = getattr(getattr(person.birth, 'location', None), 'continent', '') if person.birth else ''
        if birth_place and not birth_continent:
            logger.warning(f"Birth continent not found for {person.name}; place: {birth_place}; continent: {birth_continent}")
        people_summary.append({
            'ID': person_id,
            'Name': person.name,
            'birth_place': birth_place,
            'birth_date': person.birth.date_year() if person.birth else '',
            'birth_country': getattr(getattr(person.birth, 'location', None), 'country', '') if person.birth else '',
            'birth_continent': birth_continent,
            'death_place': person.death.place if person.death else '',
            'death_date': person.death.date_year() if person.death else '',
            'death_country': getattr(getattr(person.death, 'location', None), 'country', '') if person.death else '',
            'death_continent': getattr(getattr(person.death, 'location', None), 'continent', '') if person.death else ''
        })

    try:
        with open(output_file, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, dialect='excel')
            csv_writer.writerow(['ID', 'Name', 'birth_place', 'birth_date', 'birth_country', 'birth_continent', 'death_place', 'death_date', 'death_country', 'death_continent'])
            for summary in people_summary:
                csv_writer.writerow([summary['ID'],
                                     summary['Name'],
                                     summary['birth_place'],
                                     summary['birth_date'],
                                     summary['birth_country'],
                                     summary['birth_continent'],
                                     summary['death_place'],
                                     summary['death_date'],
                                     summary['death_country'],
                                     summary['death_continent']])
    except IOError as e:
        logger.error(f"Failed to write people summary to {output_file}: {e}")

def write_birth_death_countries_summary(args: argparse.Namespace, people: Dict[str, Any], output_file: str, gedcom_file_name: str) -> None:
    """
    Write a summary of birth and death countries to a CSV file.
    Also generates a heatmap image showing birth/death country pairs by continent.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.
        people (dict): Dictionary of people.
        output_file (str): Output CSV file path.
        gedcom_file_name (str): GEDCOM file name for labeling.
    """
    birth_death_countries_summary = {}

    for person_id, person in people.items():
        birth_location = getattr(person.birth, 'location', None) if person.birth else None
        death_location = getattr(person.death, 'location', None) if person.death else None

        birth_country = getattr(birth_location, 'country', 'none') if birth_location else 'none'
        birth_country_continent = getattr(birth_location, 'continent', 'none') if birth_location else 'none'
        death_country = getattr(death_location, 'country', 'none') if death_location else 'none'
        death_country_continent = getattr(death_location, 'continent', 'none') if death_location else 'none'

        key = (birth_country, death_country)
        if key not in birth_death_countries_summary:
            birth_death_countries_summary[key] = {'count': 0}
        birth_death_countries_summary[key]['count'] += 1
        birth_death_countries_summary[key]['birth_country'] = birth_country
        birth_death_countries_summary[key]['death_country'] = death_country
        birth_death_countries_summary[key]['birth_continent'] = birth_country_continent
        birth_death_countries_summary[key]['death_continent'] = death_country_continent

    try:
        with open(output_file, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, dialect='excel')
            csv_writer.writerow(['Birth Country', 'Birth Continent', 'Death Country', 'Death Continent', 'Count'])
            for (birth_country, death_country), data in birth_death_countries_summary.items():
                csv_writer.writerow([birth_country, data['birth_continent'], death_country, data['death_continent'], data['count']])
    except IOError as e:
        logger.error(f"Failed to write birth/death countries summary to {output_file}: {e}")

    output_image_file = os.path.splitext(output_file)[0] + "_heatmap.png"
    save_birth_death_heatmap(birth_death_countries_summary, output_image_file, gedcom_file_name)
    logger.info(f"Saved heatmap image to {output_image_file}")

def write_countries_summary(args: argparse.Namespace, people: Dict[str, Any], output_file: str, gedcom_file_name: str) -> None:
    """
    Write a summary of countries to a CSV file.
    Each row contains: Country, Country Code, Continent, Count.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.
        people (dict): Dictionary of people.
        output_file (str): Output CSV file path.
        gedcom_file_name (str): GEDCOM file name for labeling.
    """
    countries_summary = {}

    for person in people.values():
        birth = person.birth
        birth_location = getattr(birth, 'location', None) if birth and birth.place else None
        if birth_location:
            country_code = getattr(birth_location, 'country_code', '').upper()
            country = getattr(birth_location, 'country', '')
            continent = getattr(birth_location, 'continent', '')
            if country:
                if country not in countries_summary:
                    countries_summary[country] = {'count': 0, 'country_code': country_code, 'continent': continent}
                countries_summary[country]['count'] += 1

    try:
        with open(output_file, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, dialect='excel')
            csv_writer.writerow(['Country', 'Country Code', 'Continent', 'Count'])
            for country, data in countries_summary.items():
                csv_writer.writerow([country, data.get('country_code', ''), data.get('continent', ''), data['count']])
    except IOError as e:
        logger.error(f"Failed to write countries summary to {output_file}: {e}")

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

def save_birth_death_heatmap(birth_death_countries_summary: Dict[Any, Any], output_image_file: str, gedcom_file_name: str) -> None:
    """
    Generate and save a heatmap image showing birth/death country pairs by continent.
    Adds a footer with filename and total number of people.

    Args:
        birth_death_countries_summary (dict): Summary of birth/death country pairs.
        output_image_file (str): Output image file path.
        gedcom_file_name (str): GEDCOM file name for labeling.
    """
    # Prepare data for DataFrame
    records = []
    for (birth_country, death_country), data in birth_death_countries_summary.items():
        birth_continent = data['birth_continent']
        death_continent = data['death_continent']
        records.append({
            'Birth Continent': birth_continent,
            'Birth Country': birth_country,
            'Death Continent': death_continent,
            'Death Country': death_country,
            'Count': data['count']
        })

    # Move records with 'none' as continent to the start
    records = (
        [rec for rec in records if rec['Birth Continent'] == 'none' or rec['Death Continent'] == 'none'] +
        [rec for rec in records if rec['Birth Continent'] != 'none' and rec['Death Continent'] != 'none']
    )

    # Get a combined set of birth and death continents
    colours = ['red', 'blue', 'green', 'purple', 'orange', 'teal', 'brown', 'black']
    all_continents = set(rec['Birth Continent'] for rec in records) | set(rec['Death Continent'] for rec in records)
    continent_colours = {continent: colour for continent, colour in zip(all_continents, colours)}

    df = pd.DataFrame(records)
    heatmap_df = df.pivot_table(
        index=['Birth Continent', 'Birth Country'],
        columns=['Death Continent', 'Death Country'],
        values='Count',
        fill_value=0,
        aggfunc='sum'
    )

    num_people = int(df['Count'].sum())

    plt.figure(figsize=(max(10, heatmap_df.shape[1] * 0.5), max(8, heatmap_df.shape[0] * 0.5)))
    ax = sns.heatmap(
        heatmap_df, annot=False, fmt='d', cmap='Blues', cbar=False,
        cbar_kws={'label': 'Count'}, linewidths=0.5, linecolor='gray'
    )
    xlabel_text = ax.set_xlabel('Death Country', color='red')
    ylabel_text = ax.set_ylabel('Birth Country', color='blue')
    plt.title(f'{gedcom_file_name} : Birth & Death Country Heatmap (by Continent)')

    fig = plt.gcf()
    fig.canvas.draw() # Needed to compute text position

    label_obj = ax.xaxis.label
    bbox = label_obj.get_window_extent(fig.canvas.get_renderer())
    inv = ax.transData.inverted()
    _ , y0 = inv.transform((bbox.x0, bbox.y0))
    _ , y1 = inv.transform((bbox.x1, bbox.y1))
    xlabel_height = abs(y1 - y0)
    
    label_obj = ax.yaxis.label
    bbox = label_obj.get_window_extent(fig.canvas.get_renderer())
    inv = ax.transData.inverted()
    x0, _ = inv.transform((bbox.x0, bbox.y0))
    x1, _ = inv.transform((bbox.x1, bbox.y1))
    ylabel_width = abs(x1 - x0)

    # Set blank tick labels (we'll draw our own centered labels)
    ax.set_xticks([])
    ax.set_yticks([])

    # Add count numbers to each cell with auto-scaled font size to fit in the cell
    heatmap = heatmap_df.values
    nrows, ncols = heatmap.shape
    im = ax.collections[0]

    # Get axis size in inches and figure DPI
    bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    ax_width_in, ax_height_in = bbox.width, bbox.height
    cell_width_in = ax_width_in / ncols
    cell_height_in = ax_height_in / nrows
    # Convert to points (1 inch = 72 points)
    cell_width_pt = cell_width_in * 72
    cell_height_pt = cell_height_in * 72

    gap_pixels = 30

    for i in range(nrows):
        for j in range(ncols):
            count = heatmap[i, j]
            if count > 0:
                # Choose white or black font depending on background intensity
                bg_intensity = im.cmap(im.norm(count))
                r, g, b = bg_intensity[:3]
                luminance = 0.299 * r + 0.587 * g + 0.114 * b
                font_color = 'black' if luminance > 0.5 else 'white'

                num_digits = len(str(count))

                # Estimate font size: fit width and height, and adjust for digit count
                font_size_w = cell_width_pt / (num_digits * 1.0)
                font_size_h = cell_height_pt * 1.0
                font_size = min(font_size_w, font_size_h)
                font_size = max(6, min(font_size, 14))  # Clamp between 6 and 14

                ax.text(
                    j + 0.5, i + 0.5, str(count),
                    ha='center', va='center',
                    color=font_color,
                    fontsize=font_size,
                    fontweight='bold',
                    clip_on=True
                )

    # Draw country labels beside x-axis, centered below each column
    label_heights = []
    country_labels_y = len(heatmap_df.index) + 2*xlabel_height
    for j, col in enumerate(heatmap_df.columns):
        text_obj = ax.annotate(
            col[1],
            xy=(j + 0.5, country_labels_y), xycoords=('data', 'data'),
            ha='center', va='top',
            fontsize=10, fontweight='normal', rotation=90, clip_on=False
        )
        # Get bounding box in display coordinates
        bbox = text_obj.get_window_extent()
        # Convert height from pixels to data coordinates
        inv = ax.transData.inverted()
        x0, y0 = inv.transform((bbox.x0, bbox.y0))
        x1, y1 = inv.transform((bbox.x1, bbox.y1))
        label_heights.append(abs(y1 - y0))
        gap_y = abs(inv.transform((0, gap_pixels))[1] - inv.transform((0, 0))[1])
    max_label_height = max(label_heights) if label_heights else 0

    # Draw country labels beside y-axis, centered on each row
    label_widths = []
    country_labels_x = -2*ylabel_width
    for i, idx in enumerate(heatmap_df.index):
        text_obj = ax.annotate(
            idx[1],
            xy=(country_labels_x, i + 0.5), xycoords=('data', 'data'),
            ha='right', va='center',
            fontsize=10, fontweight='normal', rotation=0, clip_on=False
        )
        # Get bounding box in display coordinates
        bbox = text_obj.get_window_extent()
        # Convert width from pixels to data coordinates
        inv = ax.transData.inverted()
        x0, y0 = inv.transform((bbox.x0, bbox.y0))
        x1, y1 = inv.transform((bbox.x1, bbox.y1))
        label_widths.append(abs(x1 - x0))
        gap_x = abs(inv.transform((gap_pixels, 0))[0] - inv.transform((0, 0))[0])
    max_label_width = max(label_widths) if label_widths else 0

    # Improved group (continent) labels below x-axis
    group_positions_x = {}
    line_y = country_labels_y + max_label_height + 2*gap_y
    continent_labels_y = line_y + gap_y
    for i, g in enumerate(heatmap_df.columns.get_level_values(0)):
        group_positions_x.setdefault(g, []).append(i)
    for idx, (group, positions) in enumerate(group_positions_x.items()):
        start = min(positions)
        end = max(positions)
        x = (start + end + 1) / 2
        colour = continent_colours.get(group, 'black')
        ax.annotate(
            group,
            xy=(x, continent_labels_y), xycoords=('data', 'data'),
            ha='center', va='top',
            fontsize=12, fontweight='bold', color=colour, rotation=90,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7)
        )
        # Draw horizontal lines (in alternating colours) to show the size of each group
        ax.plot(
            [start + 0.2, end + 1 - 0.2],  [line_y, line_y], # +1 so the line covers the full group
            color=colour, linewidth=2, solid_capstyle='round', clip_on=False
        )

    # Improved group (continent) labels beside y-axis
    group_positions_y = {}
    line_x = country_labels_x - max_label_width - gap_x
    continent_labels_x = line_x - gap_x
    for i, g in enumerate(heatmap_df.index.get_level_values(0)):
        group_positions_y.setdefault(g, []).append(i)
    for idx, (group, positions) in enumerate(group_positions_y.items()):
        start = min(positions)
        end = max(positions)
        y = (start + end + 1) / 2
        colour = continent_colours.get(group, 'black')
        ax.annotate(
            group,
            xy=(continent_labels_x, y), xycoords=('data', 'data'),
            ha='right', va='center',
            fontsize=12, fontweight='bold', color=colour,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7)
        )
        # Draw vertical lines (in alternating colours) to show the size of each group
        ax.plot(
            [line_x, line_x], [start + 0.2, end + 1 - 0.2],  # +1 so the line covers the full group
            color=colour, linewidth=2, solid_capstyle='round', clip_on=False
        )

    fig.canvas.draw() # Needed to compute text position

    # Add footer text with filename root and total number of people
    footer_text = f"File: {gedcom_file_name}   |   Total people: {num_people}   |   (including spouses)"
    plt.figtext(
        0.01, 0.01, footer_text,
        ha='left', va='bottom',
        fontsize=10, color='gray'
    )

    plt.tight_layout()
    plt.savefig(output_image_file)
    plt.close()

def main() -> None:
    """
    Main entry point for the gedmap script.
    Parses arguments, processes GEDCOM files, geolocates places, writes summaries and KML output.
    """
    parser = get_arg_parser()
    args = parser.parse_args()
    if not args.input_files:
        parser.error("At least one input file is required")

    # Set logging level before any logging calls
    if args.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.ERROR)

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
            args.always_geocode,
            args.verbose,
        )

        my_gedcom = GeolocatedGedcom(
            gedcom_file=str(gedcom_file),
            geocoder=geocoder,
            default_country=args.default_country,
            always_geocode=args.always_geocode,
            verbose=args.verbose,
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
        logger.error(f"An error occurred: {e}", exc_info=True)