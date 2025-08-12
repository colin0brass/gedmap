from operator import inv
import os
import re
import csv

import argparse
import tempfile

import pandas as pd
import seaborn as sns

from ged4py.parser import GedcomReader

from geocode import Geocode

from gedcom import GedcomParser
from kml import KML_Life_Lines_Creator

default_country='England'

parser = argparse.ArgumentParser(
    description='convert gedcom to kml file and lookup addresses')
parser.add_argument('input_files', type=str, nargs='+',
    help='One or more GEDCOM files to process')
parser.add_argument('--default_country', type=str, default=default_country,
    help='Default country for geocoding, or "none" to disable')
parser.add_argument('--always-geocode', action='store_true',
    help='always geocode, ignore cache')
parser.add_argument('--geo_cache_filename', type=str, default='geo_cache.csv',
    help='geo-location cache filename to use, defaults to geo_cache.csv')
parser.add_argument('--write_places_summary', action='store_true',
    help='save places summary')
parser.add_argument('--write_people_summary', action='store_true',
    help='save people summary')
parser.add_argument('--write_countries_summary', action='store_true',
    help='save countries summary')
parser.add_argument('--write_all', action='store_true',
    help='save all summaries')
parser.add_argument('--verbose', action='store_true',
    help='verbose output')

def geolocate_all(args, gedcom_parser, geocoder):
    full_geolocation_dict = gedcom_parser.get_full_place_dict()

    for place, data in full_geolocation_dict.items():
        location = geocoder.lookup_location(place)
        continent = location.get('continent', '')
        if not continent or continent.strip().lower() in ('', 'none'):
            location['continent'] = geocoder.country_code_to_continent(location.get('country_code', ''))

        full_geolocation_dict[place]['location'] = location

    return full_geolocation_dict

def write_places_summary(args, full_geolocation_dict, output_file):
    with open(output_file, 'w', newline='') as csvfile:
        csv_header = ['count', 'latitude', 'longitude', 'found_country', 'has_date', 'place']
        csv_writer = csv.writer(csvfile, dialect='excel')
        csv_writer.writerow(csv_header)
        for place, data in full_geolocation_dict.items():
            latitude = data.get('location', {}).get('latitude', '')
            longitude = data.get('location', {}).get('longitude', '')
            found_country = data.get('location', {}).get('found_country', '')
            has_date = data.get('has_date', False)
            r = [data['count'], latitude, longitude, found_country, has_date, place]
            csv_writer.writerow(r)
            
def write_people_summary(args, people, output_file):
    people_summary = []
    for person_id, person in people.items():
        birth_place = person.birth.place if person.birth else ''
        birth_continent = person.birth.location.get('continent', '') if (person.birth and getattr(person.birth, 'location', None)) else ''
        if birth_place and not birth_continent:
            print(f"Birth continent not found for {person.name}; place: {birth_place}; continent: {birth_continent}")
        people_summary.append({
            'ID': person_id,
            'Name': person.name,
            'birth_place': person.birth.place if person.birth else '',
            'birth_date': person.birth.date_year() if person.birth else '',
            'birth_country': person.birth.location.get('country', '') if (person.birth and getattr(person.birth, 'location', None)) else '',
            'birth_continent': person.birth.location.get('continent', '') if (person.birth and getattr(person.birth, 'location', None)) else '',
            'death_place': person.death.place if person.death else '',
            'death_date': person.death.date_year() if person.death else '',
            'death_country': person.death.location.get('country', '') if (person.death and getattr(person.death, 'location', None)) else '',
            'death_continent': person.death.location.get('continent', '') if (person.death and getattr(person.death, 'location', None)) else ''
        })

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

def write_birth_death_countries_summary(args, people, output_file, gedcom_file_name):
    birth_death_countries_summary = {}

    for person_id in people.keys():
        person = people[person_id]
        found_birth_country = False
        found_death_country = False

        if person.birth:
            birth_location = person.birth.location if person.birth.location else None
            if birth_location:
                if birth_location:
                    birth_country = birth_location.get('country', '')
                    birth_country_continent = birth_location.get('continent', '')
                    found_birth_country = True

        if person.death:
            death_location = person.death.location if person.death.location else None
            if death_location:
                if death_location:
                    death_country = death_location.get('country', '')
                    death_country_continent = death_location.get('continent', '')
                    found_death_country = True

        if not found_birth_country:
            birth_country = 'none'
            birth_country_continent = 'none'
        if not found_death_country:
            death_country = 'none'
            death_country_continent = 'none'

        if birth_country and death_country:
            key = (birth_country, death_country)
            if key not in birth_death_countries_summary:
                birth_death_countries_summary[key] = {'count': 0}
            birth_death_countries_summary[key]['count'] += 1
            birth_death_countries_summary[key]['birth_country'] = birth_country
            birth_death_countries_summary[key]['death_country'] = death_country
            birth_death_countries_summary[key]['birth_continent'] = birth_country_continent
            birth_death_countries_summary[key]['death_continent'] = death_country_continent

    with open(output_file, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile, dialect='excel')
        csv_writer.writerow(['Birth Country', 'Birth Continent', 'Death Country', 'Death Continent', 'Count'])
        for (birth_country, death_country), data in birth_death_countries_summary.items():
            csv_writer.writerow([birth_country, data['birth_continent'], death_country, data['death_continent'], data['count']])

    # After writing the CSV in write_birth_death_countries_summary:
    output_image_file = os.path.splitext(output_file)[0] + "_heatmap.png"
    save_birth_death_heatmap(birth_death_countries_summary, output_image_file, gedcom_file_name)
    print(f"Saved heatmap image to {output_image_file}")

def write_countries_summary(args, people, output_file, gedcom_file_name):
    countries_summary = {}

    for person_id in people.keys():
        person = people[person_id]
        birth = person.birth
        if birth and birth.place:
            birth_location = person.birth.location if person.birth.location else None
            if birth_location:
                country_code = birth_location.get('country_code', '').upper()
                country = birth_location.get('country', '')
                continent = birth_location.get('continent', '')
                if country:
                    if country not in countries_summary:
                        countries_summary[country] = {'count': 0, 'country_code': country_code, 'continent': continent}
                    countries_summary[country]['count'] += 1

    with open(output_file, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile, dialect='excel')
        csv_writer.writerow(['Country', 'Country Code', 'Continent', 'Count'])
        for country, data in countries_summary.items():
            csv_writer.writerow([country, data.get('country_code', ''), data.get('continent', ''), data['count']])

import matplotlib.pyplot as plt
import numpy as np

def save_birth_death_heatmap(birth_death_countries_summary, output_image_file, gedcom_file_name):

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
        heatmap_df, annot=False, fmt='d', cmap='Blues', cbar=False, # remove the colourbar (legend)
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
    im = ax.collections[0]  # The QuadMesh from seaborn's heatmap

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

LINE_RE = re.compile(
    r'^(\d+)\s+(?:@[^@]+@\s+)?([A-Z0-9_]+)(.*)$'
)  # allow optional @xref@ before the tag

def fix_gedcom_conc_cont_levels(input_path):
    temp_fd, temp_path = tempfile.mkstemp(suffix='.ged')
    os.close(temp_fd)

    cont_level = None

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
            else:
                cont_level = level + 1
                outfile.write(raw)
    return temp_path

def write_kml(args, people, output_file):
    kml_life_lines_creator = KML_Life_Lines_Creator(output_file, people, verbose=args.verbose)
    # kml_life_lines_creator.add_default_location_if_unknown(main_person_id)
    kml_life_lines_creator.add_people()
    kml_life_lines_creator.connect_parents()

    # main_person_id = list(people.keys())[0]  # default to first person in list for now
    # kml_life_lines_creator.lookat_person(main_person_id)

    kml_life_lines_creator.save_kml()

def main():
    args = parser.parse_args()
    if not args.input_files:
        parser.error("At least one input file is required")

    for input_file in args.input_files:
        path_dir = os.path.dirname(input_file)
        base_file_name = os.path.splitext(os.path.basename(input_file))[0]

        print('Reading GEDCOM file:', input_file)
        fixed_gedcom_file = fix_gedcom_conc_cont_levels(input_file)
        gedcom_parser = GedcomParser(
            gedcom_file=fixed_gedcom_file,
            default_country=args.default_country,
            always_geocode=args.always_geocode,
            verbose=args.verbose,
            location_cache_file=args.geo_cache_filename
        )

        print('Geolocating all places...')
        geocoder = Geocode(
            args.geo_cache_filename,
            args.default_country,
            args.always_geocode,
            args.verbose,
            args.geo_cache_filename
        )
        geolocation_dict = geolocate_all(args, gedcom_parser, geocoder)
        geocoder.save_address_cache()  # Save any cached locations

        people = gedcom_parser.parse_people() # doing this after geolocation and saving cache

        print('Writing KML file...')
        output_file = os.path.join(path_dir, f"{base_file_name}.kml")
        write_kml(args, people, output_file)

        if args.write_places_summary or args.write_all:
            output_file = os.path.join(path_dir, f"{base_file_name}_places.csv")
            print(f"Writing places summary to {output_file}")
            write_places_summary(args, geolocation_dict, output_file)

        if args.write_people_summary or args.write_all:
            output_file = os.path.join(path_dir, f"{base_file_name}_people.csv")
            print(f"Writing people summary to {output_file}")
            write_people_summary(args, people, output_file)

        if args.write_countries_summary or args.write_all:
            output_file = os.path.join(path_dir, f"{base_file_name}_countries.csv")
            print(f"Writing countries summary to {output_file}")
            write_birth_death_countries_summary(args, people, output_file, base_file_name)

if __name__ == "__main__":
    main()