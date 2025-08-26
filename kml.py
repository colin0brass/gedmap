from typing import Dict
import datetime

import simplekml as simplekml

from lat_lon import LatLon
from gedcom import GeolocatedGedcom, Person

class KmlExporter:
    line_width = 2
    timespan_default_start_year = 1950
    timespan_default_range_years = 100
    marker_style = {
        'Birth': {
            'icon_href': 'http://maps.google.com/mapfiles/kml/paddle/pink-blank.png'
        },
        'Marriage': {
            'icon_href': 'http://maps.google.com/mapfiles/kml/paddle/grn-blank.png',
        },
        'Death': {
            'icon_href': 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png',
        }
    }

    def __init__(self, kml_file):
        self.kml_file = kml_file
        self.kml = simplekml.Kml()
#         self.max_line_weight = 20
        self.kml_folders = dict()

        for marker_type in self.marker_style.keys():
            self.marker_style[marker_type]['style'] = simplekml.Style()
            self.marker_style[marker_type]['style'].iconstyle.icon.href = self.marker_style[marker_type]['icon_href']
            self.marker_style[marker_type]['style'].name = marker_type

            self.kml_folders[marker_type] = self.kml.newfolder(name=marker_type)

    def finalise(self):
        if not self.kml:
            print('KML not initialised')
        else:
            print('Saving KML file:', self.kml_file)
            self.kml.save(self.kml_file)

    def add_point(self, marker_type: str, name: str, lat_lon: LatLon, timestamp: str, description: str):
        id = None
        if lat_lon.lat is not None and lat_lon.lon is not None:
            # pnt = self.kml.newpoint(name=name,
            pnt = self.kml_folders[marker_type].newpoint(name=name,
                coords=[(lat_lon.lon, lat_lon.lat)],
                description=description)
            if timestamp:
                pnt.timestamp.when = timestamp
            if marker_type in self.marker_style.keys():
                pnt.style = self.marker_style[marker_type]['style']
            point_id = pnt.id # this returns the ID of the point, however that is wrapped-up in a Placemark which has id+1
            placemark_id = pnt.placemark.id
        return placemark_id, point_id

    def draw_line(self, name: str, begin_lat_lon: LatLon, end_lat_lon: LatLon,
                    begin_date: str, end_date: str,
                    colour: simplekml.Color = simplekml.Color.white):
        kml_line = {id:None}
        if begin_lat_lon.lat is not None and end_lat_lon.lat is not None:
            kml_line = self.kml.newlinestring(name=name, coords=[
                (begin_lat_lon.lon, begin_lat_lon.lat), (end_lat_lon.lon, end_lat_lon.lat)])
            kml_line.timespan.begin = begin_date
            kml_line.timespan.end   = end_date
            kml_line.altitudemode   = simplekml.AltitudeMode.clamptoground
            kml_line.extrude        = 1
            kml_line.tessellate     = 1 # this was needed before line was visible over terrain
            kml_line.style.linestyle.color  = colour
            kml_line.style.linestyle.width  = self.line_width
        return kml_line.id
    
    def lookat(self, lat_lon: LatLon, begin_year: int, end_year: int, altitude=0, range=1000, heading=0, tilt=0):
        if lat_lon.lat is not None and lat_lon.lon is not None:
            lookat = simplekml.LookAt(
                latitude=lat_lon.lat, longitude=lat_lon.lon,
                altitude=altitude, range=range,
                heading=heading, tilt=tilt
            )
            self.kml.document.lookat = lookat # default lookat

class KML_Life_Lines_Creator:
    place_type_list = ['Birth', 'Marriage', 'Death'] # 'native'

    def __init__(self, kml_file, gedcom: GeolocatedGedcom, use_hyperlinks=True, main_person_id=None, verbose=False):
        self.kml_instance = KmlExporter(kml_file)
        self.gedcom = gedcom
        self.kml_point_to_person_lookup = dict()
        self.kml_person_to_point_lookup = dict()
        self.kml_person_to_placemark_lookup = dict()
        self.use_hyperlinks = use_hyperlinks
        self.main_person_id = main_person_id
        self.verbose = verbose

    def _add_point(self, current, event, event_type):
        if event and getattr(event.location, 'lat_lon', None):
            if event.location.lat_lon.lat is not None and event.location.lat_lon.lon is not None:
                description =  '{} {}<br>{}<br>'.format(event_type, event.date_year(), event.place)
                placemark_id, point_id = self.kml_instance.add_point(event_type, current.name, event.location.lat_lon, event.date_year(), description)
                self.kml_point_to_person_lookup[point_id] = current.xref_id
                self.kml_person_to_point_lookup[current.xref_id] = point_id
                self.kml_person_to_placemark_lookup[current.xref_id] = placemark_id

    # using date_year() since not yet figured out how to extract a parsable full date from life event
    def add_person(self, current: Person):
        if current.birth and getattr(current.birth.location, 'lat_lon', None):
            self._add_point(current, current.birth, "Birth")
        for marriage_event in current.marriages:
            if marriage_event and getattr(marriage_event.location, 'lat_lon', None):
                self._add_point(current, marriage_event, "Marriage")
        if current.death and getattr(current.death.location, 'lat_lon', None):
            self._add_point(current, current.death, "Death")

    def update_person_description(self, point: simplekml.featgeom.Point, current: Person):
        description = point.description
        if current.birth and current.birth.location.lat_lon:
            if current.father and (current.father in self.kml_person_to_point_lookup):
                father_id = self.kml_person_to_placemark_lookup[current.father]
                if father_id:
                    if self.use_hyperlinks:
                        description += 'Father: <a href=#{};balloonFlyto>{}</a><br>'.format(
                            father_id, self.gedcom.people[current.father].name)
                    else:
                        description += 'Father: {}<br>'.format(self.gedcom.people[current.father].name)
            if current.mother and (current.mother in self.kml_person_to_point_lookup):
                mother_id = self.kml_person_to_placemark_lookup[current.mother]
                if mother_id:
                    if self.use_hyperlinks:
                        description += 'Mother: <a href=#{};balloonFlyto>{}</a><br>'.format(
                            mother_id, self.gedcom.people[current.mother].name)
                    else:
                        description += 'Mother: {}<br>'.format(self.gedcom.people[current.mother].name)
            if current.children:
                description += 'Children: '
                for child in current.children:
                    if child in self.kml_person_to_placemark_lookup:
                        child_id = self.kml_person_to_placemark_lookup[child]
                        description += '<a href=#{};balloonFlyto>{}</a> '.format(
                            child_id, self.gedcom.people[child].name)
                    else:
                        description += '{} '.format(self.gedcom.people[child].name)
            point.description = description

    def add_people(self):
        # simplekml "id" property is read-only, so create all people points first, and store lookup-dict of IDs,
        # then update with descriptions and relationships

        for p in self.gedcom.people.keys():
            person = self.gedcom.people[p]
            self.add_person(person)

        for g in self.kml_instance.kml.geometries:
            person = self.gedcom.people[self.kml_point_to_person_lookup[g.id]]
            self.update_person_description(g, person)

    def connect_parents(self):
        line_name = ''

        for p in self.gedcom.people.keys():
            person = self.gedcom.people[p]
            if self.verbose: print('person: ', person)

            if person.lat_lon and person.lat_lon.lat is not None:
                begin_date = None # initial value
                if person.birth:
                    if person.birth.date:
                        begin_date = person.birth.date_year()

                if person.father:
                    father = self.gedcom.people[person.father]
                    if father.lat_lon and father.lat_lon.lat is not None:
                        end_date = None # initial value
                        if father.birth:
                            if father.birth.date:
                                end_date = father.birth.date_year()
                        line_id = self.kml_instance.draw_line(line_name, person.lat_lon, father.lat_lon,
                                        begin_date, end_date,
                                        simplekml.Color.blue)

                if person.mother:
                    mother = self.gedcom.people[person.mother]
                    if mother.lat_lon and mother.lat_lon.lat is not None:
                        end_date = None # initial value
                        if mother.birth:
                            if mother.birth.date:
                                end_date = mother.birth.date_year()
                        line_id = self.kml_instance.draw_line(line_name, person.lat_lon, mother.lat_lon,
                                        begin_date, end_date,
                                        simplekml.Color.red)

    def lookat_person(self, person_id: str):
        if person_id in self.gedcom.people.keys():
            person = self.gedcom.people[person_id]
            if person.lat_lon and person.lat_lon.lat is not None:
                lat_lon = person.lat_lon
                begin_year = person.birth.date_year() if person.birth and person.birth.date else None
                end_year = person.death.date_year() if person.death and person.death.date else None
                self.kml_instance.lookat(lat_lon=lat_lon, begin_year=begin_year, end_year=end_year)

    def save_kml(self):
        self.kml_instance.finalise()
