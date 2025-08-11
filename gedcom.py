# notes from gedKml.pl:
    # "Father: <a href=#I100;balloonFlyto>name</a>"
    # file:///Users/OsborneFamily/Files%20outside%20of%20iCloud%20-%20check%20if%20need%20to%20keep/Scripting/Mapping/ancestorsRobertEdwardOsborne_160207.kml#I100;balloonFlyto
    # used extensions of the person ID in name field to distinguish (and allow hyperlinks to) different life events:
    # -1 for birth; -2 for death

    # looks as though simplekml doesn't allow setting if "placemark ID"
    # https://stackoverflow.com/questions/67325123/change-the-tag-id-attribute-in-kml-simplekml

import re

from typing import Dict

from ged4py.parser import GedcomReader
from ged4py.model import Record, NameRec

from geocode import Geocode

from lat_lon import LatLon

class LifeEvent:
    def __init__(self, place : str, atime, lat_lon : LatLon=None, what=None):
        self.where = place
        self.when = atime
        self.lat_lon = lat_lon
        self.what = what

    def __repr__(self):
        return '[ {} : {} ]'.format(self.when, self.where)

    def when_year(self, last = False):
        if self.when:
            if (type(self.when) == type(' ')):
                return (self.when)
            else:
                if self.when.value.kind.name == 'RANGE' or self.when.value.kind.name == 'PERIOD':
                    if last:
                        return self.when.value.date1.year_str
                    else:
                        return self.when.value.date2.year_str
                elif self.when.value.kind.name == 'PHRASE':
                    try:
                        return re.search(r'[0-9]{4}', self.when.value.phrase)[0] # to improve
                    except:
                        print('LifeEvent: when_year: Warning: unable to parse date phrase: ', self.when.value.phrase)
                        return None
                else:
                    return self.when.value.date.year_str
        return None

    def __getattr__(self, name):
        if name == 'pos':
            return (None, None)
        return None


class Person:
    def __init__(self, xref_id):
        self.xref_id = xref_id
        self.name = None
        self.father : Person = None
        self.mother : Person = None
        self.children = [] # should be list of Person
        self.lat_lon : LatLon = None
        self.birth : LifeEvent = None
        self.death : LifeEvent = None
        self.marriage = None # should add list
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
        if self.birth and self.birth.when: best_year = 'Born {}'.format(self.birth.when_year())
        if self.death and self.death.when: best_year = 'Died {}'.format(self.death.when_year())
        return best_year


class GedcomParser:
    default_country = 'England'

    def __init__(self, gedcom_file=None, default_country=default_country, always_geocode=False, verbose=False, location_cache_file=None):
        self.gedcom_file = gedcom_file
        self.always_geocode = always_geocode
        self.default_country = default_country
        self.verbose = verbose
        self.location_cache_file = location_cache_file
        self.geocode_lookup = Geocode(
            cache_file=location_cache_file,
            default_country=default_country,
            always_geocode=always_geocode,
            verbose=verbose,
            location_cache_file=location_cache_file,
        )
        
    def close(self):
        self.geocode_lookup.close()

    def get_place(record: Record, placetag = 'PLAC'):
        place_value = None
        if record:
            place = record.sub_tag(placetag)
            if place: place_value = place.value
        return place_value

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

#         # photo
#         obj = record.sub_tag('OBJE')
#         person.photo = None
#         if (obj):
#             isjpg = obj.sub_tag('FORM') and obj.sub_tag('FORM').value == 'jpg'
#             if (isjpg):
#                 person.photo = obj.sub_tag('FILE').value

        person.sex = record.sex
        birth = record.sub_tag('BIRT')
        if birth:
#             print('birth:', birth)
            place = GedcomParser.get_place(birth)
            person.birth = LifeEvent(place, birth.sub_tag('DATE'))
            place_tag = birth.sub_tag('PLAC')
            found_lat_lon = False
            if place_tag:
                map = place_tag.sub_tag('MAP')
                if map:
                    lat = map.sub_tag('LATI')
                    lon = map.sub_tag('LONG')
                    if lat and lon:
                        person.lat_lon = LatLon(lat.value, lon.value)
                        person.birth.lat_lon = LatLon(lat.value, lon.value)
                        found_lat_lon = True
            if not found_lat_lon:
                if place:
                    # location = Geocode().lookup_location(place)
                    location = self.geocode_lookup.lookup_location(place)
                    if location and location['latitude'] and location['longitude']:
                        person.lat_lon = LatLon(location['latitude'], location['longitude'])
                        person.birth.lat_lon = LatLon(location['latitude'], location['longitude'])
                    # person.lat_lon = Geocode().lookup_location(place)
                    # if person.lat_lon:
                    #     person.birth.lat_lon = person.lat_lon
                    # else:
                    #     person.birth.lat_lon = None
                else:
                    person.birth.lat_lon = None

        # to add marriage and death locations, and potential residence locations too

        return person

    def __create_people(self, records0) -> Dict[str, Person]:
        people = dict()
        for record in records0('INDI'):
#             print(record)
            # people[record.xref_id] = GedcomParser.__create_person(record)
            people[record.xref_id] = self.__create_person(record)
#             print('{}: {}'.format(record.xref_id, people[record.xref_id]))
        for record in records0('FAM'):
            husband = record.sub_tag('HUSB')
            wife = record.sub_tag('WIFE')
            for child in record.sub_tags('CHIL'):
                if child.xref_id in people.keys():
#                     print('record:', record)
#                     print('husband:', husband)
#                     print('wife:', wife)
#                     print('child:', people[child.xref_id])
                    if people[child.xref_id]:
                        if husband:
                            people[child.xref_id].father = husband.xref_id
                            people[husband.xref_id].children.append(child.xref_id)
                        if wife:
                            people[child.xref_id].mother = wife.xref_id
                            people[wife.xref_id].children.append(child.xref_id)
#         print('GedcomParser: __create_people : people=', people)
        return people

    def parse_people(self) -> Dict[str, Person]:
        with GedcomReader(self.gedcom_file) as parser:
            return self.__create_people(parser.records0)
