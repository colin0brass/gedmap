"""
geocode.py - Geocoding utilities for GEDCOM mapping.

Handles geocoding, country/continent lookup, and caching of location results.
Loads fallback continent mappings from geocode.yaml.
"""

import os
import csv
import re
import time
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from unidecode import unidecode
import yaml

import pycountry
import pycountry_convert as pc
import yaml  # Ensure PyYAML is installed
from geopy.geocoders import Nominatim

from postal.expand import expand_address
from postal.parser import parse_address

from location import LatLon, Location
from addressbook import FuzzyAddressBook
from geocache import GeoCache

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)


class Canonical:

    SPACE_RE = re.compile(r"\s+")
    PUNC_RE = re.compile(r"[\,;]+")

    
    def __init__(self, geo_config_path: Optional[Path] = None):
        """
        Initialize Canonical with country data from pycountry and optional config file.

        Args:
            geo_config_path (Optional[Path]): Path to geocode.yaml configuration file.
        """
        self.countrynames = []
        self.countrynames_lower = []
        self.country_name_to_code_dict = {}
        self.country_code_to_continent_dict = {}
        self.country_code_to_name_dict = {}
        self.country_code_to_continent_dict = {}
        self.country_substitutions = {}
        self.default_country = None
        self.fallback_continent_map = {}

        self.__geo_config = {}

        if geo_config_path:
            self.load_geo_config(geo_config_path)

    def load_geo_config(self, geo_config_path: Optional[Path]) -> None:
        if geo_config_path and geo_config_path.exists():
            try:
                with open(geo_config_path, 'r', encoding='utf-8') as f:
                    self.__geo_config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load geo config from {geo_config_path}: {e}")
                self.__geo_config = {}
        else:
            self.__geo_config = {}

        self.country_substitutions = self.__geo_config.get('country_substitutions', {})
        self.default_country = self.__geo_config.get('default_country', '')
        additional_countries_codes_dict_to_add = self.__geo_config.get('additional_countries_codes_dict_to_add', {})
        self.fallback_continent_map = self.__geo_config.get('fallback_continent_map', {})

        additional_countries_to_add = list(additional_countries_codes_dict_to_add.keys())
        self.countrynames = [country.name for country in pycountry.countries]
        self.countrynames.extend(additional_countries_to_add)

        self.countrynames_lower = [name.lower() for name in self.countrynames]

        self.country_name_to_code_dict = {country.name: country.alpha_2 for country in pycountry.countries}
        self.country_name_to_code_dict.update(additional_countries_codes_dict_to_add)

        self.country_code_to_name_dict = {v: k for k, v in self.country_name_to_code_dict.items()}
        self.country_code_to_continent_dict = {code: self.country_code_to_name_dict.get(code) for code in self.country_code_to_name_dict.keys()}


    def __strip_and_norm(self, address: str) -> str:
        if not address: return ""
        address = unidecode(address)
        address = address.strip()
        address = self.PUNC_RE.sub(",", address)
        address = self.SPACE_RE.sub(" ", address)
        return address

    def __expand_variants(self, address: str, max_variants=8) -> List[str]:
        variants = list(expand_address(address))[:max_variants]
        return variants if variants else [address]
    
    def __parse_address(self, address: str) -> List[tuple]:
        parsed = dict(parse_address(address))
        return {k: self.__strip_and_norm(v) for v, k in parsed.items()}
    
    def __canonical_city(self, city: str) -> str:
        """ Returns the longest variant of the city name after stripping and normalizing. """
        # placeholder for potential future improved lookup and matching
        city_clean = self.__strip_and_norm(city)
        city_variants = self.__expand_variants(city_clean)
        best_variant = max(city_variants, key=len)
        return best_variant
    
    def __canonical_country(self, country: str) -> str:
        """ Returns the longest variant of the country name after stripping and normalizing. """
        # placeholder for potential future improved lookup and matching
        country_clean = self.__strip_and_norm(country)
        country_variants = self.__expand_variants(country_clean)
        best_variant = max(country_variants, key=len)
        return best_variant
    
    def __canonicalise_parts(self, parts: Dict[str, str]) -> (Dict):
        ordered_keys = ['house_number', 'road', 'suburb', 'city', 'state', 'postcode', 'country']
        canonical_parts = {key: parts.get(key, '') for key in ordered_keys if parts.get(key)}
        canonical_parts['city'] = self.__canonical_city(canonical_parts.get('city', ''))
        canonical_parts['country'] = self.__canonical_country(canonical_parts.get('country', ''))
        segments = list(canonical_parts.values())
        # Remove duplicates while preserving order
        segments = [s for i,s in enumerate(segments) if s and s not in segments[:i]]
        canonical_address = ', '.join(segments)
        return canonical_parts, canonical_address

    def get_canonical(self, address: str) -> Tuple[str, Dict[str, str]]:
        address_clean = self.__strip_and_norm(address)
        address_variants = self.__expand_variants(address_clean)
        best_variant_canonical = None
        best_len = -1 # initial value
        for variant in address_variants:
            address_parts = self.__parse_address(variant)
            address_parts, address_canonical = self.__canonicalise_parts(address_parts)
            # prefer the variant with city and country, and the longest overall length
            if 'city' in address_parts and 'country' in address_parts:
                if len(address_canonical) > best_len:
                    best_variant_canonical = address_canonical
                    best_len = len(address_canonical)

        return best_variant_canonical, address_parts

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

        place_lower = place.lower()
        last_place_element = place_lower.split(',')[-1].strip()

        for key in self.country_substitutions:
            if last_place_element == key.lower():
                new_country = self.country_substitutions[key]
                logger.info(f"Substituting country '{last_place_element}' with '{new_country}' in place '{place}'")
                place_lower = place_lower.replace(last_place_element, new_country)
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
            place_lower = place_lower + ', ' + self.default_country
            country_name = self.default_country

        country_code = self.country_name_to_code_dict.get(country_name, 'none')
        return (place_lower, country_code, country_name, found)
    
class Geocode:
    """
    Handles geocoding logic, cache management, and country/continent lookups for addresses.

    Attributes:
        always_geocode (bool): If True, always geocode and ignore cache.
        location_cache_file (str): Path to cache file.
        geo_cache (GeoCache): Geocoded location cache manager.
        ... (other attributes)
    """
    __slots__ = [
        'default_country', 'always_geocode', 'location_cache_file', 'additional_countries_codes_dict_to_add',
        'additional_countries_to_add', 'country_substitutions', 'geo_cache',
        'geolocator', 'canonical', 'countrynames', 'countrynames_lower', 'country_name_to_code_dict',
        'country_code_to_name_dict', 'country_code_to_continent_dict', 'fallback_continent_map'
    ]
    geocode_sleep_interval = 1  # Delay due to Nominatim request limit

    def __init__(
        self,
        cache_file: str,
        default_country: Optional[str] = None,
        always_geocode: bool = False,
        alt_place_file_path: Optional[Path] = None,
        geo_config_path: Optional[Path] = None
    ):
        """
        Initialize the Geocode object, loading country info and cache.

        Args:
            cache_file (str): Path to cache file.
            always_geocode (bool): Ignore cache if True.
            alt_place_cache (Dict[str, dict]): Alternative place names cache.
            use_alt_places (bool): Whether to use alternative place names.
            alt_place_file_path (Optional[Path]): Alternative place names file path.
            geo_config_path (Optional[Path]): Path to geocode.yaml configuration file.
        """
        self.default_country = default_country
        self.always_geocode = always_geocode
        self.location_cache_file = cache_file

        self.geo_cache = GeoCache(cache_file, always_geocode, alt_place_file_path)
        self.geolocator = Nominatim(user_agent="gedcom_geocoder")

        self.canonical = Canonical(geo_config_path)

    def save_geo_cache(self) -> None:
        """
        Save address cache if applicable.
        """
        if self.geo_cache.location_cache_file:
            self.geo_cache.save_geo_cache()

    def get_address_and_countrycode(self, address: str) -> Tuple[str, str, str, bool]:
        """
        Given an address string, return (address, country_code, country_name, found).

        Args:
            address (str): Address string.

        Returns:
            Tuple[str, str, str, bool]: (address, country_code, country_name, found)
        """
        found = False
        country_name = ''

        address_lower = address.lower()
        last_address_element = address_lower.split(',')[-1].strip()

        for key in self.canonical.country_substitutions:
            if last_address_element == key.lower():
                new_country = self.canonical.country_substitutions[key]
                logger.info(f"Substituting country '{last_address_element}' with '{new_country}' in address '{address}'")
                address_lower = address_lower.replace(last_address_element, new_country)
                country_name = new_country
                found = True
                break

        if last_address_element in self.canonical.countrynames_lower:
            found = True
            for name in self.canonical.countrynames:
                if name.lower() == last_address_element:
                    country_name = name
                    break

        if not found and self.canonical.default_country.lower() != 'none':
            logger.info(f"Adding default country '{self.canonical.default_country}' to address '{address}'")
            address_lower = address_lower + ', ' + self.canonical.default_country
            country_name = self.canonical.default_country

        country_code = self.canonical.country_name_to_code_dict.get(country_name, 'none')
        return (address_lower, country_code, country_name, found)

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
            location = Location(
                used=1,
                latitude=geo_location.latitude,
                longitude=geo_location.longitude,
                country_code=country_code.upper(),
                country_name=country_name,
                continent=self.country_code_to_continent_dict.get(country_code, ''),
                found_country=bool(found_country),
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
        Separate addresses into cached and non-cached.

        Args:
            address_book (FuzzyAddressBook): Address book containing full addresses.

        Returns:
            Tuple[Dict[str, dict], Dict[str, dict]]: (cached_places, non_cached_places)
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

        use_place_name = place
        cache_entry = None
        if not self.always_geocode:
            use_place_name, cache_entry = self.geo_cache.lookup_geo_cache_entry(place)

        default_country = self.canonical.default_country if self.canonical.default_country else ''

        (place_with_country, country_code, country_name, found_country) = self.canonical.get_place_and_countrycode(use_place_name)
        canonical, parts = self.canonical.get_canonical(use_place_name)
        if cache_entry and not self.always_geocode:
            if cache_entry.get('latitude') and cache_entry.get('longitude'):
                found_in_cache = True
                location = Location.from_dict(cache_entry)
                location.canonical_addr = canonical
                location.canonical_parts = parts
                if cache_entry.get('found_country', False) == False or cache_entry.get('country_name', '') == '':
                    if found_country:
                        logger.info(f"Found country in cache for {use_place_name}, but it was not marked as found.")
                        location.found_country = True
                        location.country_code = country_code.upper()
                        location.country_name = country_name
                        location.continent = self.canonical.country_code_to_continent_dict.get(country_code, "Unknown")
                        self.geo_cache.add_geo_cache_entry(place, location)
                    else:
                        logger.info(f"Unable to add country from geo cache lookup for {use_place_name}")
                if not found_country:
                    logger.info(f"Country not found in cache for {use_place_name}, using default country: {default_country}")

        if not found_in_cache:
            location = self.geocode_address(place_with_country, country_code, country_name, found_country, address_depth=0)
            if location is not None:
                location.address = place
                self.geo_cache.add_geo_cache_entry(place, location)
                logger.info(f"Geocoded {place} to {location.lat_lon}")

        if location:
            continent = location.continent
            if not continent or continent.strip().lower() in ('', 'none'):
                location.continent = self.canonical.country_code_to_continent_dict.get(location.country_code, "Unknown")

        return location