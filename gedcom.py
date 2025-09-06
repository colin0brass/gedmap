"""
gedcom.py - GEDCOM data model and parser.

Defines classes for representing people, life events, and parsing GEDCOM files.
Supports geolocation integration and KML export.
"""

import os
import csv
import re
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ged4py.parser import GedcomReader
from ged4py.model import Record, NameRec

from geocode import Geocode
from location import LatLon, Location
from addressbook import FuzzyAddressBook

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)

class LifeEvent:
    """
    Represents a life event (birth, death, marriage, etc.) for a person.

    Attributes:
        place (str): The place where the event occurred.
        date: The date of the event (can be string or ged4py date object).
        what: The type of event (e.g., 'BIRT', 'DEAT').
        record (Record): The GEDCOM record associated with the event.
        location (Location): Geocoded location object.
        lat_lon (LatLon): Latitude/longitude of the event, if available.
    """
    __slots__ = [
        'place',
        'date',
        'what',
        'record',
        'location',
        'lat_lon'
    ]

    def __init__(self, place: str, atime, lat_lon: Optional[LatLon] = None, what=None, record: Optional[Record] = None):
        """
        Initialize a LifeEvent.

        Args:
            place (str): Place of the event.
            atime: Date of the event.
            lat_lon (Optional[LatLon]): Latitude/longitude.
            what: Type of event.
            record (Optional[Record]): GEDCOM record.
        """
        self.place = place
        self.date = atime
        self.what = what
        self.record = record
        self.location = None
        self.lat_lon = lat_lon

    def __repr__(self) -> str:
        return f'[ {self.date} : {self.place} ]'

    def date_year(self, last: bool = False) -> Optional[str]:
        """
        Returns the year string for the event date.

        Args:
            last (bool): If True, returns the last year in a range.

        Returns:
            Optional[str]: Year string or None.
        """
        if self.date:
            if isinstance(self.date, str):
                return self.date
            else:
                kind = getattr(self.date.value, 'kind', None)
                if kind and kind.name in ('RANGE', 'PERIOD'):
                    if last:
                        return self.date.value.date1.year_str
                    else:
                        return self.date.value.date2.year_str
                elif kind and kind.name == 'PHRASE':
                    try:
                        return re.search(r'[0-9]{4}', self.date.value.phrase)[0]
                    except Exception:
                        logger.warning(f'LifeEvent: date_year: unable to parse date phrase: {self.date.value.phrase}')
                        return None
                else:
                    return getattr(self.date.value.date, 'year_str', None)
        return None

    def __getattr__(self, name):
        if name == 'pos':
            return (None, None)
        return None

class Person:
    """
    Represents a person in the GEDCOM file.

    Attributes:
        xref_id (str): GEDCOM cross-reference ID.
        name (str): Full name.
        father (Optional[str]): Father's xref ID.
        mother (Optional[str]): Mother's xref ID.
        children (List[str]): List of children xref IDs.
        lat_lon (Optional[LatLon]): Latitude/longitude.
        birth (Optional[LifeEvent]): Birth event.
        death (Optional[LifeEvent]): Death event.
        marriages (List[LifeEvent]): Marriage events.
        firstname (str): First name.
        surname (str): Surname.
        maidenname (str): Maiden name.
        sex (str): Sex.
    """
    __slots__ = [
        'xref_id',
        'name',
        'father',
        'mother',
        'children',
        'lat_lon',
        'birth',
        'death',
        'marriages',
        'firstname',
        'surname',
        'maidenname',
        'sex'
    ]

    def __init__(self, xref_id: str):
        """
        Initialize a Person.

        Args:
            xref_id (str): GEDCOM cross-reference ID.
        """
        self.xref_id = xref_id
        self.name = None
        self.father: Optional[str] = None
        self.mother: Optional[str] = None
        self.children: List[str] = []
        self.lat_lon: Optional[LatLon] = None
        self.birth: Optional[LifeEvent] = None
        self.death: Optional[LifeEvent] = None
        self.marriages: List[LifeEvent] = []
        self.firstname = None
        self.surname = None
        self.maidenname = None
        self.sex = None

    def __repr__(self) -> str:
        return f'[ {self.xref_id} : {self.name} - {self.father} {self.mother} - {self.lat_lon} ]'

    def ref_year(self) -> str:
        """
        Returns a reference year string for the person.

        Returns:
            str: Reference year string.
        """
        if self.birth and self.birth.date:
            return f'Born {self.birth.date_year()}'
        if self.death and self.death.date:
            return f'Died {self.death.date_year()}'
        return 'Unknown'

class GedcomParser:
    """
    Parses GEDCOM files and extracts genealogical data.

    Attributes:
        gedcom_file (Path): Path to GEDCOM file.
        ... (other attributes)
    """

    LINE_RE = re.compile(r'^(0|[1-9][0-9]*)\s+([A-Z0-9_]+)(.*)$')

    def __init__(self, gedcom_file: Path = None):
        """
        Initialize GedcomParser.

        Args:
            gedcom_file (Path): Path to GEDCOM file.
        """
        self.gedcom_file = self.check_fix_gedcom(gedcom_file)

    def close(self):
        """Placeholder for compatibility."""
        pass

    def check_fix_gedcom(self, input_path: Path) -> Path:
        """Fixes common issues in GEDCOM records."""
        temp_fd, temp_path = tempfile.mkstemp(suffix='.ged')
        os.close(temp_fd)
        changed = self.fix_gedcom_conc_cont_levels(input_path, temp_path)
        if changed:
            logger.warning(f"Checked and made corrections to GEDCOM file '{input_path}' saved as {temp_path}")
        return temp_path if changed else input_path

    def fix_gedcom_conc_cont_levels(self, input_path: Path, temp_path: Path) -> bool:
        """
        Fixes GEDCOM continuity and structure levels.
        These types of GEDCOM issues have been seen from Family Tree Maker exports.
        If not fixed, they can cause failure to parse the GEDCOM file correctly.
        """

        cont_level = None
        changed = False

        try:
            with open(input_path, 'r', encoding='utf-8', newline='') as infile, \
                open(temp_path, 'w', encoding='utf-8', newline='') as outfile:
                for raw in infile:
                    line = raw.rstrip('\r\n')
                    m = self.LINE_RE.match(line)
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
        return changed

    @staticmethod
    def get_place(record: Record, placetag: str = 'PLAC') -> Optional[str]:
        """
        Extracts the place value from a record.

        Args:
            record (Record): GEDCOM record.
            placetag (str): Tag to extract.

        Returns:
            Optional[str]: Place value or None.
        """
        place_value = None
        if record:
            place = record.sub_tag(placetag)
            if place:
                place_value = place.value
        return place_value

    def __get_event_location(self, record: Record) -> Optional[LifeEvent]:
        """
        Creates a LifeEvent from a record.

        Args:
            record (Record): GEDCOM record.

        Returns:
            Optional[LifeEvent]: LifeEvent object or None.
        """
        event = None
        if record:
            place = GedcomParser.get_place(record)
            event = LifeEvent(place, record.sub_tag('DATE'), record=record)
        return event

    def __create_person(self, record: Record) -> Person:
        """
        Creates a Person object from a record.

        Args:
            record (Record): GEDCOM record.

        Returns:
            Person: Person object.
        """
        person = Person(record.xref_id)
        person.name = ''
        name: NameRec = record.sub_tag('NAME')
        if name:
            person.firstname = record.name.first
            person.surname = record.name.surname
            person.maidenname = record.name.maiden
            person.name = f'{record.name.format()}'
        if person.name == '':
            person.firstname = 'Unknown'
            person.surname = 'Unknown'
            person.maidenname = 'Unknown'
            person.name = 'Unknown'
        person.sex = record.sex
        person.birth = self.__get_event_location(record.sub_tag('BIRT'))
        person.death = self.__get_event_location(record.sub_tag('DEAT'))
        return person

    def __create_people(self, records0) -> Dict[str, Person]:
        """
        Creates a dictionary of Person objects from records.

        Args:
            records0: GEDCOM records.

        Returns:
            Dict[str, Person]: Dictionary of Person objects.
        """
        people = {}
        for record in records0('INDI'):
            people[record.xref_id] = self.__create_person(record)
        return people

    def __add_marriages(self, people: Dict[str, Person], records) -> Dict[str, Person]:
        """
        Adds marriage and parent/child relationships to people.

        Args:
            people (Dict[str, Person]): Dictionary of Person objects.
            records: GEDCOM records.

        Returns:
            Dict[str, Person]: Updated dictionary of Person objects.
        """
        for record in records('FAM'):
            husband_record = record.sub_tag('HUSB')
            wife_record = record.sub_tag('WIFE')
            husband = people.get(husband_record.xref_id) if husband_record else None
            wife = people.get(wife_record.xref_id) if wife_record else None
            for marriage in record.sub_tags('MARR'):
                marriage_event = self.__get_event_location(marriage)
                if marriage_event:
                    if husband:
                        husband.marriages.append(marriage_event)
                    if wife:
                        wife.marriages.append(marriage_event)
            for child in record.sub_tags('CHIL'):
                if child.xref_id in people:
                    if people[child.xref_id]:
                        if husband:
                            people[child.xref_id].father = husband.xref_id
                            husband.children.append(child.xref_id)
                        if wife:
                            people[child.xref_id].mother = wife.xref_id
                            wife.children.append(child.xref_id)
        return people

    def parse_people(self) -> Dict[str, Person]:
        """
        Parses people from the GEDCOM file.

        Returns:
            Dict[str, Person]: Dictionary of Person objects.
        """
        people = {}
        try:
            with GedcomReader(str(self.gedcom_file)) as parser:
                records = parser.records0
                people = self.__create_people(records)
                people = self.__add_marriages(people, records)
        except Exception as e:
            logger.error(f"Error parsing GEDCOM file '{self.gedcom_file}': {e}")
        return people

    def get_full_address_list(self) -> List[str]:
        """
        Returns a list of all unique places found in the GEDCOM file.

        Returns:
            List[str]: List of unique place names.
        """
        address_list = []
        try:
            with GedcomReader(str(self.gedcom_file)) as g:
                # Individuals: collect PLAC under any event (BIRT/DEAT/BAPM/MARR/etc.)
                for indi in g.records0("INDI"):
                    for ev in indi.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            address_list.append(place)

            with GedcomReader(str(self.gedcom_file)) as g:
                # Individuals: collect PLAC under any event (BIRT/DEAT/BAPM/MARR/etc.)
                for indi in g.records0("INDI"):
                    for ev in indi.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            address_list.append(place)

                # Families: marriage/divorce places, etc.
                for fam in g.records0("FAM"):
                    for ev in fam.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            address_list.append(place)
        except Exception as e:
            logger.error(f"Error extracting places from GEDCOM file '{self.gedcom_file}': {e}")
        return address_list

class Gedcom:
    """
    Main GEDCOM handler for people and places.

    Attributes:
        gedcom_parser (GedcomParser): GEDCOM parser instance.
        people (Dict[str, Person]): Dictionary of Person objects.
        address_list (List[str]): List of unique place names.
    """
    __slots__ = [
        'gedcom_parser',
        'people',
        'address_list'
    ]
    def __init__(self, gedcom_file: Path):
        """
        Initialize Gedcom.

        Args:
            gedcom_file (Path): Path to GEDCOM file.
        """
        self.gedcom_parser = GedcomParser(
            gedcom_file=gedcom_file
        )
        self.people: Dict[str, Person] = {}

    def close(self):
        """Close the GEDCOM parser."""
        self.gedcom_parser.close()

    def parse_people(self) -> Dict[str, Person]:
        """
        Parse people from the GEDCOM file.

        Returns:
            Dict[str, Person]: Dictionary of Person objects.
        """
        self.people = self.gedcom_parser.parse_people()
        return self.people

    def read_full_address_list(self) -> None:
        """
        Get all places from the GEDCOM file.

        Returns:
            List[str]: List of unique place names.
        """
        self.address_list = self.gedcom_parser.get_full_address_list()

class GeolocatedGedcom(Gedcom):
    """
    GEDCOM handler with geolocation support.

    Attributes:
        geocoder (Geocode): Geocode instance.
        address_book (FuzzyAddressBook): Address book of places.
    """
    __slots__ = [
        'geocoder',
        'address_book',
        'alt_place_file_path',
        'geo_config_path'
    ]
    geolocate_all_logger_interval = 20
    
    def __init__(
            self,
            gedcom_file: Path,
            location_cache_file: Path,
            default_country: Optional[str] = None,
            always_geocode: Optional[bool] = False,
            use_alt_places: Optional[bool] = False,
            alt_place_file_path: Optional[Path] = None,
            geo_config_path: Optional[Path] = None
    ):
        """
        Initialize GeolocatedGedcom.

        Args:
            gedcom_file (str): Path to GEDCOM file.
            location_cache_file (str): Location cache file.
            default_country (Optional[str]): Default country for geocoding.
            always_geocode (Optional[bool]): Whether to always geocode.
            use_alt_places (Optional[bool]): Whether to use alternative place names.
        """
        super().__init__(gedcom_file)

        self.address_book = FuzzyAddressBook()

        self.geocoder = Geocode(
            cache_file=location_cache_file,
            default_country=default_country,
            always_geocode=always_geocode,
            alt_place_file_path=alt_place_file_path if use_alt_places else None,
            geo_config_path=geo_config_path if geo_config_path else None
        )

        self.read_full_address_book()
        self.geolocate_all()
        self.parse_people()

    def save_location_cache(self) -> None:
        """
        Save the location cache to the specified file.
        """
        self.geocoder.save_geo_cache()

    def geolocate_all(self) -> None:
        """
        Geolocate all places in the GEDCOM file.
        """
        cached_places, non_cached_places = self.geocoder.separate_cached_locations(self.address_book)
        logger.info(f"Found {cached_places.len()} cached places, {non_cached_places.len()} non-cached places.")

        logger.info(f"Geolocating {cached_places.len()} cached places...")
        for place, data in cached_places.addresses().items():
            use_place = data.alt_addr if data.alt_addr else place
            location = self.geocoder.lookup_location(use_place)
            self.address_book.add_address(place, location)
        num_non_cached_places = non_cached_places.len()

        logger.info(f"Geolocating {num_non_cached_places} non-cached places...")
        for place in non_cached_places.addresses().keys():
            logger.info(f"- {place}...")
        for idx, (place, data) in enumerate(non_cached_places.addresses().items(), 1):
            use_place = data.alt_addr if data.alt_addr else place
            location = self.geocoder.lookup_location(use_place)
            self.address_book.add_address(place, location)
            if idx % self.geolocate_all_logger_interval == 0 or idx == num_non_cached_places:
                logger.info(f"Geolocated {idx} of {num_non_cached_places} non-cached places...")
                
        logger.info(f"Geolocation of all {self.address_book.len()} places completed.")

    def parse_people(self) -> None:
        """
        Parse and geolocate all people in the GEDCOM file.
        """
        super().parse_people()
        self.geolocate_people()

    def read_full_address_book(self) -> None:
        """
        Get all places from the GEDCOM file.
        """
        super().read_full_address_list()
        for place in self.address_list:
            if not self.address_book.get_address(place):
                # location = self.geocoder.lookup_location(place)
                location = None
                self.address_book.add_address(place, location)

    def geolocate_people(self) -> None:
        """
        Geolocate birth, marriage, and death events for all people.
        """
        for person in self.people.values():
            found_location = False
            if person.birth:
                event = self.__geolocate_event(person.birth)
                person.birth.location = event.location
                if not found_location and event.location and event.location.lat_lon and event.location.lat_lon.is_valid():
                    person.lat_lon = event.location.lat_lon
                    found_location = True
            for marriage_event in person.marriages:
                event = self.__geolocate_event(marriage_event)
                marriage_event.location = event.location
                if not found_location and event.location and event.location.lat_lon and event.location.lat_lon.is_valid():
                    person.lat_lon = event.location.lat_lon
                    found_location = True
            if person.death:
                event = self.__geolocate_event(person.death)
                person.death.location = event.location
                if not found_location and event.location and event.location.lat_lon and event.location.lat_lon.is_valid():
                    person.lat_lon = event.location.lat_lon
                    found_location = True

    def __geolocate_event(self, event: LifeEvent) -> LifeEvent:
        """
        Geolocate a single event. If no location is found, event.location remains None.

        Args:
            event (LifeEvent): The event to geolocate.

        Returns:
            LifeEvent: The event with updated location and lat_lon if found.
        """
        record = getattr(event, 'record', None)
        if record:
            place_tag = record.sub_tag('PLAC')
            if place_tag:
                map_tag = place_tag.sub_tag('MAP')
                if place_tag.value:
                    location = self.geocoder.lookup_location(place_tag.value)
                    event.location = location
                if map_tag:
                    lat = map_tag.sub_tag('LATI')
                    lon = map_tag.sub_tag('LONG')
                    if lat and lon:
                        latlon = LatLon(lat.value, lon.value)
                        event.lat_lon = latlon if latlon.is_valid() else None
                    else:
                        event.lat_lon = None
            else:
                logger.info(f"No place tag found for event in record {record}")
        else:
            logger.warning("No record found for event")
        return event