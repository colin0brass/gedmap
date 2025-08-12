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
parser.add_argument('--write_place_summary', action='store_true',
    help='save place summary')
parser.add_argument('--write_person_summary', action='store_true',
    help='save person summary')
parser.add_argument('--verbose', action='store_true',
    help='verbose output')


def write_places_to_csv(counts, output_file):
    with open(output_file, 'w', newline='') as csvfile:
        csv_header = ['count', 'latitude', 'longitude', 'found_country', 'has_date', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
        csv_writer = csv.writer(csvfile, dialect='excel')
        csv_writer.writerow(csv_header)
        for place, data in counts.items():
            place_array = place.split(',')
            place_array = [p.strip() for p in place_array]
            location = data.get('location', {})
            latitude = location.get('latitude') if location else ''
            longitude = location.get('longitude') if location else ''
            found_country = location.get('found_country') if location else ''
            has_date = data.get('has_date', False)
            r = [data['count'], latitude, longitude, found_country, has_date] + list(reversed(place_array))
            csv_writer.writerow(r)

def write_place_summary(args, path, output_file):
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
                    has_date = counts[place].get('has_date', False)
                    if ev.sub_tag_value("DATE"): has_date = True
                    counts[place]['has_date'] = has_date

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
                    has_date = counts[place].get('has_date', False)
                    if ev.sub_tag_value("DATE"): has_date = True
                    counts[place]['has_date'] = has_date

    geocoder.close() # give chance for wrap-up, including saving any cached locations
    write_places_to_csv(counts, output_file)

def write_person_summary(args, path, output_file):
    people_summary = {}
    with GedcomReader(path) as g:
        for indi in g.records0("INDI"):
            name = indi.sub_tag_value("NAME")
            if name:
                people_summary[indi.xref_id] = {'name': name}
            birth = indi.sub_tag('BIRT')
            if birth:
                if birth.sub_tag('DATE'): people_summary[indi.xref_id]['has_date'] = True
                if birth.sub_tag('PLAC'): people_summary[indi.xref_id]['has_place'] = True
                people_summary[indi.xref_id]['birth_place'] = birth.sub_tag_value('PLAC') if birth.sub_tag('PLAC') else ''
                people_summary[indi.xref_id]['birth_date'] = birth.sub_tag_value('DATE') if birth.sub_tag('DATE') else ''

    with open(output_file, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile, dialect='excel')
        csv_writer.writerow(['ID', 'Name', 'has_date', 'has_place', 'birth_place', 'birth_date'])
        for person_id, indi in people_summary.items():
            csv_writer.writerow([person_id,
                                 indi.get('name', ''),
                                 indi.get('has_date', False),
                                 indi.get('has_place', False),
                                 indi.get('birth_place', ''),
                                 indi.get('birth_date', '')])

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


    print('Fixing CONC/CONT levels in GEDCOM file:', args.input_file)
    fixed_gedcom_file = fix_gedcom_conc_cont_levels(args.input_file)

    print('Writing KML file...')
    ged_to_kml(args, fixed_gedcom_file)

    if args.write_place_summary:
        output_file = os.path.join(path_dir, f"{base_file_name}_places.csv")
        print(f"Writing place summary to {output_file}")
        # counts = locate_all_places(args, fixed_gedcom_file)
        # write_places_to_csv(counts, output_file)
        write_place_summary(args, fixed_gedcom_file, output_file)

    if args.write_person_summary:
        output_file = os.path.join(path_dir, f"{base_file_name}_people.csv")
        print(f"Writing person summary to {output_file}")
        write_person_summary(args, fixed_gedcom_file, output_file)

if __name__ == "__main__":
    main()