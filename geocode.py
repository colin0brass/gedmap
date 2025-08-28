import os
import csv
import time
import pycountry
import pycountry_convert as pc
import yaml  # Add PyYAML to your requirements if not already present
from geopy.geocoders import Nominatim

from lat_lon import LatLon

class Location:
    __slots__ = [
        'used', 'lat_lon', 'country_code', 'country_name', 'continent', 'found_country', 'address',
        'name', 'alt', 'country', 'region', 'type', 'class_', 'icon', 'place_id', 'boundry', 'size', 'importance'
    ]
    def __init__(self, used=0, latitude=None, longitude=None, country_code=None, country_name=None, continent=None, found_country=False, address=None,
                 name=None, alt=None, country=None, region=None, type=None, class_=None, icon=None, place_id=None, boundry=None, size=None, importance=None):
        self.used = used
        self.lat_lon = LatLon(latitude, longitude) if (latitude is not None and longitude is not None) else None
        self.country_code = country_code
        self.country_name = country_name
        self.continent = continent
        self.found_country = found_country
        self.address = address
        self.name = name
        self.alt = alt
        self.country = country
        self.region = region
        self.type = type
        self.class_ = class_
        self.icon = icon
        self.place_id = place_id
        self.boundry = boundry
        self.size = size
        self.importance = importance

    @classmethod
    def from_dict(cls, d):
        obj = cls()
        for key, value in d.items():
            # Map 'class' key to 'class_' attribute
            if key == 'class':
                setattr(obj, 'class_', value)
            elif key.lower() == 'latitude' or key.lower() == 'longitude':
                continue
            else:
                setattr(obj, key, value)
        lat_key = next((k for k in d.keys() if k.lower() == "latitude" or k.lower() == "lat"), None)
        lon_key = next((k for k in d.keys() if k.lower() == "longitude" or k.lower() == "long"), None)
        if lat_key and lon_key:
            obj.lat_lon = LatLon(d[lat_key], d[lon_key])
        obj.used = 0 # initialise to not used
        return obj

class Geocode:
    __slots__ = [
        'always_geocode', 'verbose', 'location_cache_file', 'additional_countries_codes_dict_to_add',
        'additional_countries_to_add', 'country_substitutions', 'default_country', 'address_cache',
        'geolocator', 'countrynames', 'countrynames_lower', 'country_name_to_code_dict',
        'country_code_to_name_dict', 'country_code_to_continent_dict'
    ]
    gecode_sleep_interval = 1 # insert a delay due to low request limit of free Nominatim service

    def __init__(self, cache_file, default_country=None, always_geocode=False, verbose=False, location_cache_file=None):
        self.always_geocode = always_geocode
        self.verbose = verbose
        self.location_cache_file = location_cache_file

        # Load country info from geocode.yaml
        with open(os.path.join(os.path.dirname(__file__), "geocode.yaml"), "r") as f:
            geo_config = yaml.safe_load(f)

        self.additional_countries_codes_dict_to_add = geo_config.get('additional_countries_codes_dict_to_add', {})
        self.additional_countries_to_add = list(self.additional_countries_codes_dict_to_add.keys())
        self.country_substitutions = geo_config.get('country_substitutions', {})
        self.default_country = default_country or geo_config.get('default_country', 'England')

        self.address_cache = {}
        self.read_address_cache()

        self.geolocator = Nominatim(user_agent="gedcom_geocoder")

        self.countrynames = [country.name for country in pycountry.countries]
        self.countrynames.extend(self.additional_countries_to_add)
        self.countrynames_lower = set(name.lower() for name in self.countrynames)

        self.country_name_to_code_dict = {country.name: country.alpha_2 for country in pycountry.countries}
        self.country_name_to_code_dict.update(self.additional_countries_codes_dict_to_add)
        self.country_code_to_name_dict = {v.upper(): k for k, v in self.country_name_to_code_dict.items()}
        self.country_code_to_continent_dict = {code: self.country_code_to_continent(code) for code in self.country_code_to_name_dict.keys()}

    def close(self):
        if self.location_cache_file:
            self.save_address_cache()

    def read_address_cache(self):
        self.address_cache = {}
        if self.always_geocode:
            print('Configured to ignore cache')
        else:
            if not os.path.exists(self.location_cache_file):
                print('No location cache file found:', self.location_cache_file)
            else:
                with open(self.location_cache_file, newline='', encoding='utf-8') as f:
                    csv_reader = csv.DictReader(f, dialect='excel')
                    try:
                        for line in csv_reader:
                            key = line.get('address', '').lower()
                            line['used'] = 0  # Initialize 'used' to 0 to count usage
                            self.address_cache[key] = line
                    except csv.Error as e:
                        print('Error reading location cache file {}, line {}: {}'.format(
                            self.location_cache_file, csv_reader.line_num, e))

    def save_address_cache(self):
        if not self.address_cache:
            print('No address cache to save')
            return

        with open(self.location_cache_file, 'w', newline='', encoding='utf-8') as f:
            first_item = next(iter(self.address_cache.values()))
            csv_writer = csv.DictWriter(f, fieldnames=first_item.keys(), dialect='excel')
            csv_writer.writeheader()
            for line in self.address_cache.values():
                csv_writer.writerow(line)
        print('Saved address cache to:', self.location_cache_file)

    def country_code_to_continent(self, country_code):
        try:
            continent_code = pc.country_alpha2_to_continent_code(country_code)
            continent_name = pc.convert_continent_code_to_continent_name(continent_code)
            return continent_name
        except Exception:
            return None
    
    def get_place_and_countrycode(self, place):
        found = False
        country_name = ''

        last_place_element = place.split(',')[-1].strip()

        for key in self.country_substitutions:
            if last_place_element.lower() == key.lower():
                new_country = self.country_substitutions[key]
                if self.verbose: print(f"Substituting country '{last_place_element}' with '{new_country}' in place '{place}'")
                place = place.replace(last_place_element, new_country)
                country_name = new_country
                found = True
                break

        if last_place_element in self.countrynames_lower:
            found = True
            for idx, name in enumerate(self.countrynames):
                if name.lower() == last_place_element:
                    country_name = name
                    break

        if not found:
            if self.default_country.lower() != 'none':
                if self.verbose:
                    print(f"Adding default country '{self.default_country}' to place '{place}'")
                place = place + ', ' + self.default_country
                country_name = self.default_country

        country_code = self.country_name_to_code_dict[country_name] if country_name in self.country_name_to_code_dict else 'none'
        
        return (place, country_code, country_name, found)

    def geocode_place(self, place, country_code, country_name, found_country=False, address_depth=0) -> Location | None:
        location = None

        if not place:
            return None # No place to geocode

        max_retries = 3
        for attempt in range(max_retries):
            try:
                geo_location = self.geolocator.geocode(place, country_codes=country_code, timeout=10)
                time.sleep(self.gecode_sleep_interval)
                break
            except Exception as e:
                print(f"Error geocoding {place}: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying geocode for {place} (attempt {attempt+2}/{max_retries}) after {self.gecode_sleep_interval} seconds...")
                    time.sleep(self.gecode_sleep_interval)
                else:
                    geo_location = None
                    print(f"Giving up on geocoding {place} after {max_retries} attempts.")
                    time.sleep(self.gecode_sleep_interval)

        if geo_location:
            location = Location(
                used=1,
                lat_lon = LatLon(geo_location.latitude, geo_location.longitude),
                country_code=country_code.upper(),
                country_name=country_name,
                continent=self.country_code_to_continent_dict.get(country_code, ''),
                found_country=found_country,
                address=geo_location.address
            )
        else:
            if self.verbose: print(f"Failed to geocode {place}")

        if location is None:
            if address_depth < 3:
                if self.verbose: print(f"Retrying geocode for {place} with less precision")
                parts = place.split(',')
                if len(parts) > 1:
                    less_precise_place = ','.join(parts[1:]).strip()
                    location = self.geocode_place(less_precise_place, country_code, country_name, address_depth + 1)

        return location

    def get_lat_lon(self, location : Location) -> LatLon | None:
        if not location or location.lat_lon is None or getattr(location.lat_lon, 'lat', None) is None or getattr(location.lat_lon, 'lon', None) is None:
            return None
        return location.lat_lon

    def lookup_location(self, place) -> Location | None:
        found_in_cache = False
        found_country = False
        location = None

        if not place:
            return None

        if not self.always_geocode and (place.lower() in self.address_cache):
            location = Location()
            if self.address_cache[place.lower()]['latitude'] and self.address_cache[place.lower()]['longitude']:
                found_in_cache = True
                location = Location.from_dict(self.address_cache[place.lower()])
                self.address_cache[place.lower()]['used'] += 1
                if self.verbose: print(f"Found cached location for {place}")
                (place_with_country, country_code, country_name, found_country) = self.get_place_and_countrycode(place.lower())
                location.found_country = found_country
                if self.verbose and not found_country:
                    print(f"Country not found in cache for {place}, using default country: {self.default_country}")

        if not found_in_cache:
            (place_with_country, country_code, country_name, found_country) = self.get_place_and_countrycode(place.lower())
            location = self.geocode_place(place_with_country, country_code, country_name, found_country, address_depth=0)
            if location is not None:
                location.address = place.lower() # place_with_country
                self.address_cache[place.lower()] = location
                if self.verbose: print(f"Geocoded {place} to {location.lat_lon}")

        if location:
            continent = location.continent if location else None
            if not continent or continent.strip().lower() in ('', 'none'):
                location.continent = self.country_code_to_continent_dict.get(location.country_code, "Unknown")

        return location