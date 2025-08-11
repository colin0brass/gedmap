from typing import Dict

import simplekml as simplekml

from lat_lon import LatLon
from gedcom import Person

class KmlExporter:
    line_width = 2

    def __init__(self, kml_file):
        self.kml_file = kml_file
        self.kml = simplekml.Kml()
#         self.max_line_weight = 20

    def finalise(self):
        if not self.kml:
            print('KML not initialised')
        else:
            print('Saving KML file:', self.kml_file)
            self.kml.save(self.kml_file)

    def add_point(self, name: str, lat_lon: LatLon, timestamp: str, description: str):
        id = None
        if lat_lon.lat is not None and lat_lon.lon is not None:
            pnt = self.kml.newpoint(name=name,
                coords=[(lat_lon.lon, lat_lon.lat)],
                description=description)
            if timestamp:
                pnt.timestamp.when = timestamp
            # if xref_id:
            #     pnt._kml['id'] = xref_id
            point_id = pnt.id # this returns the ID of the point, however that is wrapped-up in a Placemark which has id+1
#             id = pnt.placemark.id # tried this, but couldn't figure out how to look up placemarks in schema
            # placemark_id = pnt._kml['id']
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

class KML_Life_Lines_Creator:
    # place_type_list = {'native':'native'}
    place_type_list = {'born':'born'}

    def __init__(self, kml_file, people: Dict[str, Person], use_hyperlinks=True, main_person_id=None, verbose=False):
        self.kml_instance = KmlExporter(kml_file)
        self.people = people
        self.kml_point_to_person_lookup = dict()
        self.kml_person_to_point_lookup = dict()
        self.kml_person_to_placemark_lookup = dict()
        self.use_hyperlinks = use_hyperlinks
        self.main_person_id = main_person_id
        self.verbose = verbose

        self.elaborate_locations()

    def elaborate_locations(self):
        for p in self.people.keys():
            self.people[p].map = self.people[p].lat_lon # save original location

        for place_type in self.place_type_list:
            if (place_type == 'native'):
                for p in self.people.keys():
                    self.people[p].lat_lon = self.people[p].map
#                 print('KML native')
                nametag = ''
            elif (place_type == 'born'):
                for p in self.people.keys():
                    self.people[p].lat_lon = LatLon(None,None)
                    if self.people[p].birth:
                        if self.people[p].birth.lat_lon:
                            self.people[p].lat_lon = self.people[p].birth.lat_lon
                            if self.verbose: print('{} : born : {},{}'.format(
                                self.people[p].name,
                                self.people[p].lat_lon.lat,
                                self.people[p].lat_lon.lon))
#                 print ("KML born")
                nametag = ' (b)'
            elif (place_type == 'death'):
                for p in self.people.keys():
                    self.people[p].lat_lon = LatLon(None,None)
                    if self.people[p].death:
                        if self.people[p].death.lat_lon:
                            self.people[p].lat_lon = self.people[p].death.lat_lon
#                 print ("KML death")
                nametag = ' (d)'
            else:
                print('Unknown place_type:', place_type)

    def add_default_location_if_unknown(self, current: Person):
        # use child's location for parent if parent doesn't have location
        person = self.people[current]
#         print('person: ', person)

        if person.lat_lon:
            if person.father:
                father = self.people[person.father]
#                 print('father: ', father)
                lat_lon = father.lat_lon
                if not lat_lon or lat_lon.lat is None:
                    father.lat_lon = person.lat_lon
                self.add_default_location_if_unknown(father.xref_id)

            if person.mother:
                mother = self.people[person.mother]
#                 print('mother: ', mother)
                lat_lon = mother.lat_lon
                if not lat_lon or lat_lon.lat is None:
                    father.lat_lon = person.lat_lon
                self.add_default_location_if_unknown(mother.xref_id)

    # using when_year() since not yet figured out how to extract a parsable full date from life event
    def add_person(self, current: Person):
#         print('Life_Lines_Creator: add_person: ', current.name)
        if current.birth and current.lat_lon:
            if current.lat_lon.lat is not None and current.lat_lon.lon is not None:
#                 print('add_person: {} {},{}'.format(current.name, current.lat_lon.lat, current.lat_lon.lon))
    #             print('kml_instance.add_point: ', current.name, current.lat_lon, current.birth.when)
                description =  '{} {}<br>{}<br>'.format('Birth', current.birth.when_year(), current.birth.where)
                placemark_id, point_id = self.kml_instance.add_point(current.name, current.lat_lon, current.birth.when_year(), description)
    #             print('add_person: {} : id={}'.format(current.name, id))
                self.kml_point_to_person_lookup[point_id] = current.xref_id
                self.kml_person_to_point_lookup[current.xref_id] = point_id
                self.kml_person_to_placemark_lookup[current.xref_id] = placemark_id

    # hyperlinks not yet working to go to target person
    # in old code, the destination was a Placemark id
    # currently here it is a Point id
    # might want to try creating people pints inside Placemark using : simplekml.newplacemark()
    def update_person_description(self, point: simplekml.featgeom.Point, current: Person):
        description = point.description
        if current.birth and current.lat_lon:
            # "Father: <a href=#I100;balloonFlyto>name</a>"
            if current.father and (current.father in self.kml_person_to_point_lookup):
                # father_id = self.kml_person_to_point_lookup[current.father]
                father_id = self.kml_person_to_placemark_lookup[current.father]
                if father_id:
                    if self.use_hyperlinks: # not working yet
                        description += 'Father: <a href=#{};balloonFlyto>{}</a><br>'.format(
                            father_id, self.people[current.father].name)
                    else:
                        description += 'Father: {}<br>'.format(self.people[current.father].name)
            if current.mother and (current.mother in self.kml_person_to_point_lookup):
                mother_id = self.kml_person_to_placemark_lookup[current.mother]
                if mother_id:
                    if self.use_hyperlinks: # not working yet
                        description += 'Mother: <a href=#{};balloonFlyto>{}</a><br>'.format(
                            mother_id, self.people[current.mother].name)
                    else:
                        description += 'Mother: {}<br>'.format(self.people[current.mother].name)
            if current.children:
                description += 'Children: '
                for child in current.children:
                    if child in self.kml_person_to_placemark_lookup:
                        child_id = self.kml_person_to_placemark_lookup[child]
                        description += '<a href=#{};balloonFlyto>{}</a> '.format(
                            child_id, self.people[child].name)
                    else:
                        description += '{} '.format(self.people[child].name)
            point.description = description

    def add_people(self):
        # kml Geometry class used to create all geometry objects, however the "id" property is read-only
        # therefore create all people points first, and store lookup-dict of IDs, then update with descriptions
        # and relationships

        for p in self.people.keys():
            person = self.people[p]
            self.add_person(person)

        for g in self.kml_instance.kml.geometries:
#         print('Containers:', self.kml_instance.kml.allgeometries)
#         for g in self.kml_instance.kml.containers:
#             print(g)
            person = self.people[self.kml_point_to_person_lookup[g.id]]
            self.update_person_description(g, person)

    def connect_parents(self):
        line_name = ''

        for p in self.people.keys():
            person = self.people[p]
            if self.verbose: print('person: ', person)

            if person.lat_lon and person.lat_lon.lat is not None:
                begin_date = None # initial value
                if person.birth:
                    if person.birth.when:
                        begin_date = person.birth.when_year()

                if person.father:
                    father = self.people[person.father]
#                     print('father: ', father)
                    if father.lat_lon and father.lat_lon.lat is not None:
                        end_date = None # initial value
                        if father.birth:
                            if father.birth.when:
                                end_date = father.birth.when_year()
                        line_id = self.kml_instance.draw_line(line_name, person.lat_lon, father.lat_lon,
                                        begin_date, end_date,
                                        simplekml.Color.blue)

                if person.mother:
                    mother = self.people[person.mother]
#                     print('mother: ', mother)
                    if mother.lat_lon and mother.lat_lon.lat is not None:
                        end_date = None # initial value
                        if mother.birth:
                            if mother.birth.when:
                                end_date = mother.birth.when_year()
#                         print('mother: {} : {},{}; {}'.format(mother,mother))
                        line_id = self.kml_instance.draw_line(line_name, person.lat_lon, mother.lat_lon,
                                        begin_date, end_date,
                                        simplekml.Color.red)

    def save_kml(self):
#         print('Save KML')
        self.kml_instance.finalise()
