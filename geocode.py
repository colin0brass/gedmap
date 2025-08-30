"""
geocode.py - Geocoding utilities for GEDCOM mapping.

Handles geocoding, country/continent lookup, and caching of location results.
Loads fallback continent mappings from geocode.yaml.
"""

import os
import csv
import time
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict

import pycountry
import pycountry_convert as pc
import yaml  # Ensure PyYAML is installed
from geopy.geocoders import Nominatim

from location import LatLon, Location

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)

def load_yaml_config(path: Path) -> dict:
    """
    Load YAML configuration from the given path.

    Args:
        path (Path): Path to the YAML file.

    Returns:
        dict: Parsed YAML configuration or empty dict if not found/error.
    """
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError as e:
        logger.warning(f"Could not load geocode.yaml: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading geocode.yaml: {e}")
    return {}

class Geocode:
    """
    Handles geocoding and country/continent lookup for places.

    Attributes:
        always_geocode (bool): Ignore cache if True.
        location_cache_file (str): Path to cache file.
        default_country (str): Default country for geocoding.
        address_cache (Dict[str, dict]): Cached addresses.
        geolocator (Nominatim): Geopy geocoder instance.
        fallback_continent_map (Dict[str, str]): Fallback continent mapping from YAML.
        ... (other config attributes)
    """
    __slots__ = [
        'always_geocode', 'location_cache_file', 'additional_countries_codes_dict_to_add',
        'additional_countries_to_add', 'country_substitutions', 'default_country', 'address_cache',
        'geolocator', 'countrynames', 'countrynames_lower', 'country_name_to_code_dict',
        'country_code_to_name_dict', 'country_code_to_continent_dict', 'fallback_continent_map'
    ]
    gecode_sleep_interval = 1  # Delay due to Nominatim request limit

    def __init__(
        self,
        cache_file: str,
        default_country: Optional[str] = None,
        always_geocode: bool = False
    ):
        """
        Initialize the Geocode object, loading country info and cache.

        Args:
            cache_file (str): Path to cache file.
            default_country (Optional[str]): Default country.
            always_geocode (bool): Ignore cache if True.
        """
        self.always_geocode = always_geocode
        self.location_cache_file = cache_file

        geo_yaml_path = Path(__file__).parent / "geocode.yaml"
        geo_config = load_yaml_config(geo_yaml_path)

        self.additional_countries_codes_dict_to_add = geo_config.get('additional_countries_codes_dict_to_add', {})
        self.additional_countries_to_add = list(self.additional_countries_codes_dict_to_add.keys())
        self.country_substitutions = geo_config.get('country_substitutions', {})
        self.default_country = default_country or geo_config.get('default_country', 'England')

        # Load fallback continent map from YAML if present, else use empty dict
        self.fallback_continent_map: Dict[str, str] = geo_config.get('fallback_continent_map', {})

        self.address_cache: Dict[str, dict] = {}
        self.read_address_cache()

        self.geolocator = Nominatim(user_agent="gedcom_geocoder")

        self.countrynames = [country.name for country in pycountry.countries]
        self.countrynames.extend(self.additional_countries_to_add)
        self.countrynames_lower = set(name.lower() for name in self.countrynames)

        self.country_name_to_code_dict = {country.name: country.alpha_2 for country in pycountry.countries}
        self.country_name_to_code_dict.update(self.additional_countries_codes_dict_to_add)
        self.country_code_to_name_dict = {v.upper(): k for k, v in self.country_name_to_code_dict.items()}
        self.country_code_to_continent_dict = {code: self.country_code_to_continent(code) for code in self.country_code_to_name_dict.keys()}

    def close(self) -> None:
        """
        Save address cache if applicable.
        """
        if self.location_cache_file:
            self.save_address_cache()

    def read_address_cache(self) -> None:
        """
        Read address cache from file.
        """
        self.address_cache = {}
        if self.always_geocode:
            logger.info('Configured to ignore cache')
            return
        if not self.location_cache_file or not os.path.exists(self.location_cache_file):
            logger.info(f'No location cache file found: {self.location_cache_file}')
            return
        try:
            with open(self.location_cache_file, newline='', encoding='utf-8') as f:
                csv_reader = csv.DictReader(f, dialect='excel')
                for line in csv_reader:
                    key = line.get('address', '').lower()
                    line['used'] = 0
                    self.address_cache[key] = line
        except FileNotFoundError as e:
            logger.warning(f'Location cache file not found: {e}')
        except csv.Error as e:
            logger.error(f'CSV error reading location cache file {self.location_cache_file}: {e}')
        except Exception as e:
            logger.error(f'Error reading location cache file {self.location_cache_file}: {e}')

    def save_address_cache(self) -> None:
        """
        Save address cache to file.
        """
        if not self.address_cache:
            logger.info('No address cache to save')
            return
        try:
            # Collect all fieldnames from all cache entries
            all_fieldnames = set()
            for entry in self.address_cache.values():
                all_fieldnames.update(entry.keys())
            fieldnames = list(all_fieldnames)
            if not fieldnames:
                logger.info('Address cache is empty, nothing to save.')
                return
            with open(self.location_cache_file, 'w', newline='', encoding='utf-8') as f:
                csv_writer = csv.DictWriter(f, fieldnames=fieldnames, dialect='excel')
                csv_writer.writeheader()
                for line in self.address_cache.values():
                    csv_writer.writerow(line)
            logger.info(f'Saved address cache to: {self.location_cache_file}')
        except FileNotFoundError as e:
            logger.warning(f'Location cache file not found for saving: {e}')
        except csv.Error as e:
            logger.error(f'CSV error saving address cache: {e}')
        except Exception as e:
            logger.error(f'Error saving address cache: {e}')

    def country_code_to_continent(self, country_code: str) -> Optional[str]:
        """
        Convert country code to continent name.

        Args:
            country_code (str): Country code.

        Returns:
            Optional[str]: Continent name or None.
        """
        code = country_code.upper()
        # Use fallback mapping from YAML if present
        if code in self.fallback_continent_map:
            logger.debug(f"Using fallback continent map for code '{code}': {self.fallback_continent_map[code]}")
            return self.fallback_continent_map[code]
        try:
            continent_code = pc.country_alpha2_to_continent_code(code)
            continent_name = pc.convert_continent_code_to_continent_name(continent_code)
            return continent_name
        except Exception:
            logger.warning(f"Could not convert country code '{country_code}' to continent.")
            return "Unknown"

    def get_place_and_countrycode(self, place: str) -> Tuple[str, str, str, bool]:
        """
        Given a place string, return (place, country_code, country_name, found).

        Args:
            place (str): Place string.

        Returns:
            Tuple[str, str, str, bool]: (place, country_code, country_name, found)
        """
        found = False
        country_name = ''

        last_place_element = place.split(',')[-1].strip()

        for key in self.country_substitutions:
            if last_place_element.lower() == key.lower():
                new_country = self.country_substitutions[key]
                logger.info(f"Substituting country '{last_place_element}' with '{new_country}' in place '{place}'")
                place = place.replace(last_place_element, new_country)
                country_name = new_country
                found = True
                break

        if last_place_element in self.countrynames_lower:
            found = True
            for name in self.countrynames:
                if name.lower() == last_place_element:
                    country_name = name
                    break

        if not found and self.default_country.lower() != 'none':
            logger.info(f"Adding default country '{self.default_country}' to place '{place}'")
            place = place + ', ' + self.default_country
            country_name = self.default_country

        country_code = self.country_name_to_code_dict.get(country_name, 'none')
        return (place, country_code, country_name, found)

    def geocode_place(self, place: str, country_code: str, country_name: str, found_country: bool = False, address_depth: int = 0) -> Optional[Location]:
        """
        Geocode a place string and return a Location object.

        Args:
            place (str): Place string.
            country_code (str): Country code.
            country_name (str): Country name.
            found_country (bool): Whether country was found.
            address_depth (int): Recursion depth for less precise geocoding.

        Returns:
            Optional[Location]: Location object or None.
        """
        location = None

        if not place:
            return None

        max_retries = 3
        geo_location = None
        for attempt in range(max_retries):
            try:
                geo_location = self.geolocator.geocode(place, country_codes=country_code, timeout=10)
                time.sleep(self.gecode_sleep_interval)
                if geo_location:
                    break
            except Exception as e:
                logger.error(f"Error geocoding {place}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying geocode for {place} (attempt {attempt+2}/{max_retries}) after {self.gecode_sleep_interval} seconds...")
                    time.sleep(self.gecode_sleep_interval)
                else:
                    logger.error(f"Giving up on geocoding {place} after {max_retries} attempts.")
                    time.sleep(self.gecode_sleep_interval)

        if geo_location:
            location = Location(
                used=1,
                latitude=geo_location.latitude,
                longitude=geo_location.longitude,
                country_code=country_code.upper(),
                country_name=country_name,
                continent=self.country_code_to_continent_dict.get(country_code, ''),
                found_country=found_country,
                address=geo_location.address
            )

        if location is None and address_depth < 3:
            logger.info(f"Retrying geocode for {place} with less precision")
            parts = place.split(',')
            if len(parts) > 1:
                less_precise_place = ','.join(parts[1:]).strip()
                location = self.geocode_place(less_precise_place, country_code, country_name, address_depth + 1)

        return location

    def get_lat_lon(self, location: Optional[Location]) -> Optional[LatLon]:
        """
        Return LatLon if valid, else None.

        Args:
            location (Optional[Location]): Location object.

        Returns:
            Optional[LatLon]: LatLon object or None.
        """
        if not location or not location.lat_lon or not location.lat_lon.is_valid():
            return None
        return location.lat_lon

    def lookup_location(self, place: str) -> Optional[Location]:
        """
        Lookup a place in the cache or geocode it.

        Args:
            place (str): Place string.

        Returns:
            Optional[Location]: Location object or None.
        """
        found_in_cache = False
        found_country = False
        location = None

        if not place:
            return None

        place_lower = place.lower()
        if not self.always_geocode and (place_lower in self.address_cache):
            cache_entry = self.address_cache[place_lower]
            if cache_entry.get('latitude') and cache_entry.get('longitude'):
                found_in_cache = True
                location = Location.from_dict(cache_entry)
                cache_entry['used'] = int(cache_entry.get('used', 0)) + 1
                logger.info(f"Found cached location for {place}")
                (place_with_country, country_code, country_name, found_country) = self.get_place_and_countrycode(place_lower)
                location.found_country = found_country
                if not found_country:
                    logger.info(f"Country not found in cache for {place}, using default country: {self.default_country}")

        if not found_in_cache:
            (place_with_country, country_code, country_name, found_country) = self.get_place_and_countrycode(place_lower)
            location = self.geocode_place(place_with_country, country_code, country_name, found_country, address_depth=0)
            if location is not None:
                location.address = place_lower
                self.address_cache[place_lower] = {
                    'address': place_lower,
                    'latitude': getattr(location.lat_lon, 'lat', ''),
                    'longitude': getattr(location.lat_lon, 'lon', ''),
                    'country_code': location.country_code,
                    'country_name': location.country_name,
                    'continent': location.continent,
                    'found_country': location.found_country,
                    'used': 1
                }
                logger.info(f"Geocoded {place} to {location.lat_lon}")

        if location:
            continent = location.continent
            if not continent or continent.strip().lower() in ('', 'none'):
                location.continent = self.country_code_to_continent_dict.get(location.country_code, "Unknown")

        return location