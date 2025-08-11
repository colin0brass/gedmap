import os
import re
import csv

import argparse
import tempfile

from ged4py.parser import GedcomReader

from geocode import Geocode

from gedcom import GedcomParser
from kml import KML_Life_Lines_Creator

default_country='England'

parser = argparse.ArgumentParser(
    description='convert gedcom to kml file and lookup addresses')
parser.add_argument('input_file', type=str,
    help='GEDCOM file to process')
parser.add_argument('--default_country', type=str, default=default_country,
    help='Default country for geocoding, or "none" to disable')
parser.add_argument('--always-geocode', action='store_true',
    help='always geocode, ignore cache')
parser.add_argument('--geo_cache_filename', type=str, default='geo_cache.csv',
    help='geo-location cache filename to use, defaults to geo_cache.csv')
parser.add_argument('--full_place_summary', action='store_true',
    help='save full place summary')
parser.add_argument('--verbose', action='store_true',
    help='verbose output')


def locate_all_places(args, path):
    counts = {}
    geocoder = Geocode(args.geo_cache_filename, args.default_country, args.always_geocode, args.verbose, args.geo_cache_filename)

    with GedcomReader(path) as g:
        # Individuals: collect PLAC under any event (BIRT/DEAT/BAPM/MARR/etc.)
        for indi in g.records0("INDI"):
            for ev in indi.sub_records:
                plac = ev.sub_tag_value("PLAC")  # returns None if missing
                if plac:
                    place = plac.strip()
                    location = geocoder.lookup_location(place)
                    if place not in counts:
                        counts[place] = {'count': 1, 'location': location}
                    else:
                        counts[place]['count'] += 1

        # Families: marriage/divorce places, etc.
        for fam in g.records0("FAM"):
            for ev in fam.sub_records:
                plac = ev.sub_tag_value("PLAC")
                if plac:
                    place = plac.strip()
                    location = geocoder.lookup_location(place)
                    if place not in counts:
                        counts[place] = {'count': 1, 'location': location}
                    else:
                        counts[place]['count'] += 1

    geocoder.close()
    return counts

def write_places_to_csv(counts, output_file):
    with open(output_file, 'w', newline='') as csvfile:
        csv_header = ['count', 'latitude', 'longitude', 'found_country', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
        csv_writer = csv.writer(csvfile, dialect='excel')
        csv_writer.writerow(csv_header)
        for place, data in counts.items():
            place_array = place.split(',')
            place_array = [p.strip() for p in place_array]
            location = data.get('location', {})
            latitude = location.get('latitude') if location else ''
            longitude = location.get('longitude') if location else ''
            found_country = location.get('found_country') if location else ''
            r = [data['count'], latitude, longitude, found_country] + list(reversed(place_array))
            csv_writer.writerow(r)

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

def ged_to_kml(args, fixed_gedcom_file):
    path_dir = os.path.dirname(args.input_file)
    base_file_name = os.path.splitext(os.path.basename(args.input_file))[0]
    kml_file = os.path.join(path_dir, base_file_name + '.kml')

    print('Reading people from GEDCOM file:', args.input_file)
    gedcom_parser = GedcomParser(gedcom_file=fixed_gedcom_file, default_country=args.default_country, always_geocode=args.always_geocode, verbose=args.verbose, location_cache_file=args.geo_cache_filename)

    people = gedcom_parser.parse_people()

    if not people:
        print('No people found in GEDCOM file:', args.input_file)
        return
    else:
        print(f"Found {len(people)} people in GEDCOM file.")
        # default to first person in list for now
        main_person_id = list(people.keys())[0]
        print ("Using starting person: {} ({})".format(people[main_person_id].name, main_person_id))

        kml_life_lines_creator = KML_Life_Lines_Creator(kml_file, people, verbose=args.verbose)
        kml_life_lines_creator.add_default_location_if_unknown(main_person_id)
        kml_life_lines_creator.add_people()
        kml_life_lines_creator.connect_parents()
        # kml_life_lines_creator.lookat_person(main_person_id)
        kml_life_lines_creator.save_kml()

    gedcom_parser.close() # give chance for wrap-up, including saving any cached locations

def main():
    args = parser.parse_args()
    if not args.input_file:
        parser.error("Input file is required")

    path_dir = os.path.dirname(args.input_file)
    base_file_name = os.path.splitext(os.path.basename(args.input_file))[0]
    output_file = os.path.join(path_dir, f"{base_file_name}_places.csv")

    print('Fixing CONC/CONT levels in GEDCOM file:', args.input_file)
    fixed_gedcom_file = fix_gedcom_conc_cont_levels(args.input_file)

    print('Writing KML file...')
    ged_to_kml(args, fixed_gedcom_file)

    if args.full_place_summary:
        print(f"Writing full place summary to {output_file}")
        counts = locate_all_places(args, fixed_gedcom_file)
        write_places_to_csv(counts, output_file)

if __name__ == "__main__":
    main()