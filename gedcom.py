import re

from typing import Dict, List

from ged4py.parser import GedcomReader
from ged4py.model import Record, NameRec

from geocode import Geocode, Location

from lat_lon import LatLon
from no_new_attrs import NoNewAttrs

class LifeEvent(metaclass=NoNewAttrs):
    def __init__(self, place : str, atime, lat_lon : LatLon=None, what=None, record : Record=None):
        self.place = place
        self.date = atime
        self.lat_lon = lat_lon
        self.what = what
        self.record = record

    def __repr__(self):
        return '[ {} : {} ]'.format(self.date, self.place)

    def date_year(self, last = False):
        if self.date:
            if (type(self.date) == type(' ')):
                return (self.date)
            else:
                if self.date.value.kind.name == 'RANGE' or self.date.value.kind.name == 'PERIOD':
                    if last:
                        return self.date.value.date1.year_str
                    else:
                        return self.date.value.date2.year_str
                elif self.date.value.kind.name == 'PHRASE':
                    try:
                        return re.search(r'[0-9]{4}', self.date.value.phrase)[0] # to improve
                    except:
                        print('LifeEvent: date_year: Warning: unable to parse date phrase: ', self.date.value.phrase)
                        return None
                else:
                    return self.date.value.date.year_str
        return None

    def __getattr__(self, name):
        if name == 'pos':
            return (None, None)
        return None


class Person(metaclass=NoNewAttrs):
    def __init__(self, xref_id):
        self.xref_id = xref_id
        self.name = None
        self.father : Person = None
        self.mother : Person = None
        self.children = [] # should be list of Person
        self.lat_lon : LatLon = None
        self.birth : LifeEvent = None
        self.death : LifeEvent = None
        self.marriages = [] # list of LifeEvent
        self.firstname = None
        self.surname = None
        self.maidenname = None
        self.sex = None

    def __repr__(self):
        return '[ {} : {} - {} {} - {} ]'.format(
            self.xref_id,
            self.name,
            self.father,
            self.mother,
            self.lat_lon
        )

    def ref_year(self):
        best_year = 'Unknown'
        if self.birth and self.birth.date: best_year = 'Born {}'.format(self.birth.date.year_str())
        if self.death and self.death.date: best_year = 'Died {}'.format(self.death.date.year_str())
        return best_year


class GedcomParser(metaclass=NoNewAttrs):
    default_country = 'England'

    def __init__(self, gedcom_file=None, default_country=default_country, verbose=False):
        self.gedcom_file = gedcom_file
        self.default_country = default_country
        self.verbose = verbose

    def close(self):
        self.geocode_lookup.close()

    def get_place(record: Record, placetag = 'PLAC'):
        place_value = None
        if record:
            place = record.sub_tag(placetag)
            if place: place_value = place.value
        return place_value

    def __get_event_location(self, record: Record) -> LifeEvent:
        event = None
        if record:
            place = GedcomParser.get_place(record)
            event = LifeEvent(place, record.sub_tag('DATE'), record=record)
        return event

    def __create_person(self, record: Record) -> Person:
        person = Person(record.xref_id)
        person.name = ''
        name: NameRec = record.sub_tag('NAME')
        if name:
            person.firstname = record.name.first
            person.surname = record.name.surname
            person.maidenname  = record.name.maiden
            person.name = '{}'.format(record.name.format())
        if person.name == '':
            person.firstname = 'Unknown'
            person.surname = 'Unknown'
            person.maidenname = 'Unknown'
            person.name = 'Unknown'
            
        person.sex = record.sex
        person.birth = self.__get_event_location(record.sub_tag('BIRT'))
        person.death = self.__get_event_location(record.sub_tag('DEAT'))
        # person.marriage = self.__get_event_location(record.sub_tag('MARR'))
        # for marriage in record.sub_tags('MARR'):
        #     person.marriage.append(self.__get_event_location(marriage))

        return person

    def __create_people(self, records0) -> Dict[str, Person]:
        people = dict()
        for record in records0('INDI'):
            people[record.xref_id] = self.__create_person(record)
        return people

    def __add_marriages(self, people: Dict[str, Person], records: List[Record]):
        for record in records('FAM'):
            husband_record = record.sub_tag('HUSB')
            wife_record = record.sub_tag('WIFE')
            husband = people[husband_record.xref_id] if husband_record else None
            wife = people[wife_record.xref_id] if wife_record else None
            for marriage in record.sub_tags('MARR'):
                marriage_event = self.__get_event_location(marriage)
                if marriage_event:
                    if husband:
                        husband.marriages.append(marriage_event)
                    if wife:
                        wife.marriages.append(marriage_event)
            for child in record.sub_tags('CHIL'):
                if child.xref_id in people.keys():
                    if people[child.xref_id]:
                        if husband:
                            people[child.xref_id].father = husband.xref_id
                            people[husband.xref_id].children.append(child.xref_id)
                        if wife:
                            people[child.xref_id].mother = wife.xref_id
                            people[wife.xref_id].children.append(child.xref_id)
        return people

    def parse_people(self) -> Dict[str, Person]:
        people = dict()
        with GedcomReader(self.gedcom_file) as parser:
            records = parser.records0
            people = self.__create_people(records)
            people = self.__add_marriages(people, records)
            return people

    def get_full_place_dict(self):
        full_place_dict = {}

        with GedcomReader(self.gedcom_file) as g:
            # Individuals: collect PLAC under any event (BIRT/DEAT/BAPM/MARR/etc.)
            for indi in g.records0("INDI"):
                for ev in indi.sub_records:
                    plac = ev.sub_tag_value("PLAC")  # returns None if missing
                    if plac:
                        place = plac.strip()
                        if place not in full_place_dict:
                            full_place_dict[place] = {'count': 1, 'place': place}

            # Families: marriage/divorce places, etc.
            for fam in g.records0("FAM"):
                for ev in fam.sub_records:
                    plac = ev.sub_tag_value("PLAC")
                    if plac:
                        place = plac.strip()
                        if place not in full_place_dict:
                            full_place_dict[place] = {'count': 1, 'place': place}

        return full_place_dict
    
class Gedcom(metaclass=NoNewAttrs):
    def __init__(self, gedcom_file=None, default_country='England', verbose=False):
        self.gedcom_parser = GedcomParser(
            gedcom_file=gedcom_file,
            default_country=default_country,
            verbose=verbose
        )
        self.people = dict()
        self.full_place_dict = {}

    def close(self):
        self.gedcom_parser.close()

    def _parse_people(self):
        self.people = self.gedcom_parser.parse_people()
        return self.people

    def get_full_place_dict(self):
        self.full_place_dict = self.gedcom_parser.get_full_place_dict()
        return self.full_place_dict


class GeolocatedGedcom(Gedcom, metaclass=NoNewAttrs):
    def __init__(self, gedcom_file=None, geocoder=None, default_country='England', always_geocode=False, verbose=False, location_cache_file=None):
        super().__init__(gedcom_file, default_country, verbose)
        self.geocoder = geocoder
        self.always_geocode = always_geocode
        self.full_place_dict = {}

        self._geolocate_all()

        self._parse_people()

    def _geolocate_all(self):
        self.full_place_dict = self.gedcom_parser.get_full_place_dict()
        for place, data in self.full_place_dict.items():
            location = self.geocoder.lookup_location(place)
            self.full_place_dict[place]['location'] = location

    def _parse_people(self):
        super()._parse_people()
        self._geolocate_people()

    def _geolocate_people(self):
        for person in self.people.values():
            if person.birth:
                event = self._geolocate_event(person.birth)
                person.birth.location = event.location
                # person.birth.lat_lon = event.lat_lon
            if person.death:
                event = self._geolocate_event(person.death)
                person.death.location = event.location
                # person.death.lat_lon = event.lat_lon
            for marriage_event in person.marriages:
                event = self._geolocate_event(marriage_event)
                marriage_event.location = event.location
                # marriage_event.lat_lon = event.lat_lon

    def _geolocate_event(self, event: LifeEvent) -> LifeEvent:
        record = getattr(event, 'record', None)
        if record:
            place_tag = record.sub_tag('PLAC')
            if place_tag:
                map = place_tag.sub_tag('MAP')
                if place_tag.value:
                    location = self.geocoder.lookup_location(place_tag.value)
                    event.location = location
                if map:
                    lat = map.sub_tag('LATI')
                    lon = map.sub_tag('LONG')
                    if lat and lon:
                        event.lat_lon = LatLon(lat.value, lon.value)
                    else:
                        event.lat_lon = None

        return event