"""
geocode.py - Geocoding utilities for GEDCOM mapping.

Handles geocoding, country/continent lookup, and caching of location results.
Loads fallback continent mappings from geo_config.yaml.

Author: @colin0brass
"""

import time
import logging
import random
import re
from pathlib import Path
from typing import Optional, Tuple, Dict

import pycountry
import pycountry_convert as pc
import requests
import yaml  # Ensure PyYAML is installed
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable
from geopy.adapters import AdapterHTTPError

from .geocache import GeoCache
from .geo_config import GeoConfig

from .location import Location
from .addressbook import FuzzyAddressBook
from .geocache import GeoCache
from .canonical import Canonical

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)

GEOCODEUSERAGENT = "gedcom_geocoder"

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
        logger.warning(f"Could not load geo_config.yaml: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading geo_config.yaml: {e}")
    return {}

class Geocode:
    """
    Handles geocoding logic, cache management, canonicalization, and country/continent lookups for addresses.

    Attributes:
        default_country (str): Default country for geocoding.
        always_geocode (bool): If True, always geocode and ignore cache.
        location_cache_file (str): Path to cache file.
        geo_cache (GeoCache): Geocoded location cache manager.
        geolocator (Nominatim): Geopy Nominatim geocoder instance.
        geo_config (GeoConfig): Geographic configuration instance.
        canonical (Canonical): Canonicalization utility instance.
        include_canonical (bool): Whether to include canonical address info.
    """

    __slots__ = [
        'default_country', 'always_geocode', 'location_cache_file', 'additional_countries_codes_dict_to_add',
        'additional_countries_to_add', 'country_substitutions', 'geo_cache',
        'geolocator', 'geo_config', 'canonical', 'include_canonical'
    ]
    geocode_sleep_interval = 1  # Delay due to Nominatim request limit

    def __init__(
        self,
        cache_file: str,
        default_country: Optional[str] = None,
        always_geocode: bool = False,
        alt_place_file_path: Optional[Path] = None,
        geo_config_path: Optional[Path] = None,
        file_geo_cache_path: Optional[Path] = None,
        include_canonical: bool = False
    ):
        """
        Initialize the Geocode object, loading country info and cache.

        Args:
            cache_file (str): Path to cache file.
            default_country (str, optional): Default country for geocoding.
            always_geocode (bool): Ignore cache if True.
            alt_place_file_path (Optional[Path]): Alternative place names file path.
            geo_config_path (Optional[Path]): Path to geocode.yaml configuration file.
            file_geo_cache_path (Optional[Path]): Path to per-file geo cache.
            include_canonical (bool): Whether to include canonical address info.
        """
        self.default_country = default_country
        self.always_geocode = always_geocode
        self.location_cache_file = cache_file

        self.geo_cache = GeoCache(cache_file, always_geocode, alt_place_file_path, file_geo_cache_path)
        self.geolocator = Nominatim(user_agent="gedcom_geocoder")
        self.geo_config = GeoConfig(geo_config_path)
        self.canonical = Canonical(self.geo_config)

        self.include_canonical = include_canonical

    def save_geo_cache(self) -> None:
        """
        Save address cache to disk if applicable.
        """
        if self.geo_cache.location_cache_file:
            self.geo_cache.save_geo_cache()

    def geocode_address(self, address: str, country_code: str, country_name: str, found_country: bool = False, address_depth: int = 0) -> Optional[Location]:
        """
        Geocode an address string and return a Location object.

        Args:
            address (str): Address string.
            country_code (str): Country code.
            country_name (str): Country name.
            found_country (bool): Whether country was found.
            address_depth (int): Recursion depth for less precise geocoding.

        Returns:
            Optional[Location]: Location object or None.
        """
        location = None

        if not address:
            return None

        max_retries = 3
        geo_location = None
        for attempt in range(max_retries):
            try:
                geo_location = self.geolocator.geocode(address, country_codes=country_code, timeout=10)
                time.sleep(self.geocode_sleep_interval)
                if geo_location:
                    break
            except Exception as e:
                logger.error(f"Error geocoding {address}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying geocode for {address} (attempt {attempt+2}/{max_retries}) after {self.geocode_sleep_interval} seconds...")
                    time.sleep(self.geocode_sleep_interval)
                else:
                    logger.error(f"Giving up on geocoding {address} after {max_retries} attempts.")
                    time.sleep(self.geocode_sleep_interval)

        if geo_location:
            continent = self.geo_config.get_continent_for_country_code(country_code)
            location = Location(
                used=1,
                latitude=geo_location.latitude,
                longitude=geo_location.longitude,
                country_code=country_code.upper(),
                country_name=country_name,
                continent=continent,
                found_country=found_country,
                address=geo_location.address
            )

        if location is None and address_depth < 3:
            logger.info(f"Retrying geocode for {address} with less precision")
            parts = address.split(',')
            if len(parts) > 1:
                less_precise_address = ','.join(parts[1:]).strip()
                location = self.geocode_address(less_precise_address, country_code, country_name, found_country, address_depth + 1)

        return location

    def separate_cached_locations(self, address_book: FuzzyAddressBook) -> Tuple[FuzzyAddressBook, FuzzyAddressBook]:
        """
        Separate addresses into cached and non-cached address books.

        Args:
            address_book (FuzzyAddressBook): Address book containing full addresses.

        Returns:
            Tuple[FuzzyAddressBook, FuzzyAddressBook]: (cached_places, non_cached_places)
        """
        cached_places = FuzzyAddressBook()
        non_cached_places = FuzzyAddressBook()
        for place, data in address_book.addresses().items():
            place_lower = place.lower()
            if not self.always_geocode and (place_lower in self.geo_cache.geo_cache):
                cached_places.add_address(place, data)
            else:
                non_cached_places.add_address(place, data)
        return (cached_places, non_cached_places)

    def lookup_location(self, place: str) -> Optional[Location]:
        """
        Lookup a place in the cache or geocode it if not found.

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
        
        if place == 'Livadia,Crimea,Near Yalta,Russia':
            logger.info("Debug breakpoint")

        use_place_name = place
        cache_entry = None
        if not self.always_geocode:
            use_place_name, cache_entry = self.geo_cache.lookup_geo_cache_entry(place)

        (place_with_country, country_code, country_name, found_country) = self.geo_config.get_place_and_countrycode(use_place_name)
        if self.include_canonical:
            canonical, parts = self.canonical.get_canonical(use_place_name, country_name)
        if cache_entry and not self.always_geocode:
            if cache_entry.get('latitude') and cache_entry.get('longitude'):
                found_in_cache = True
                location = Location.from_dict(cache_entry)
                if self.include_canonical:
                    location.canonical_addr = canonical
                    location.canonical_parts = parts
                if cache_entry.get('found_country', False) == False or cache_entry.get('country_name', '') == '':
                    if found_country:
                        logger.info(f"Found country in cache for {use_place_name}, but it was not marked as found.")
                        location.found_country = True
                        location.country_code = country_code.upper()
                        location.country_name = country_name
                        location.continent = self.geo_config.get_continent_for_country_code(country_code)
                        self.geo_cache.add_geo_cache_entry(place, location)
                    else:
                        logger.info(f"Unable to add country from geo cache lookup for {use_place_name}")
                if not found_country:
                    logger.info(f"Country not found in cache for {use_place_name}")

        if not found_in_cache:
            location = self.geocode_address(place_with_country, country_code, country_name, found_country, address_depth=0)
            if location is not None:
                location.address = place
                self.geo_cache.add_geo_cache_entry(place, location)
                logger.info(f"Geocoded {place} to {location.latlon}")

        if location:
            continent = location.continent
            if not continent or continent.strip().lower() in ('', 'none'):
                location.continent = self.geo_config.get_continent_for_country_code(location.country_code)

        return location
