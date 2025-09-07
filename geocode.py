"""
geocode.py - Geocoding utilities for GEDCOM mapping.

Handles geocoding, country/continent lookup, canonicalization, and caching of location results.
"""

import os
import csv
import re
import time
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from unidecode import unidecode

from geopy.geocoders import Nominatim

from postal.expand import expand_address
from postal.parser import parse_address

from location import LatLon, Location
from addressbook import FuzzyAddressBook
from geocache import GeoCache
from geo_config import GeoConfig

logger = logging.getLogger(__name__)

class Canonical:
    """
    Provides canonicalization utilities for addresses, including normalization,
    expansion of variants, parsing, and construction of canonical address strings.

    Attributes:
        geo_config (GeoConfig): Geographic configuration instance.
    """

    SPACE_RE = re.compile(r"\s+")
    PUNC_RE = re.compile(r"[\,;]+")

    def __init__(self, geo_config: GeoConfig = None):
        """
        Initialize Canonical with country data from pycountry and optional config file.

        Args:
            geo_config (GeoConfig, optional): GeoConfig instance with geographic data.
        """
        self.geo_config = geo_config if geo_config else GeoConfig()

    def __strip_and_norm(self, address: str) -> str:
        """
        Normalize and strip an address string.

        Args:
            address (str): Address string.

        Returns:
            str: Normalized address.
        """
        if not address: return ""
        address = unidecode(address)
        address = address.strip()
        address = self.PUNC_RE.sub(",", address)
        address = self.SPACE_RE.sub(" ", address)
        return address

    def __expand_variants(self, address: str, max_variants=8) -> List[str]:
        """
        Expand address variants using libpostal.

        Args:
            address (str): Address string.
            max_variants (int): Maximum number of variants to return.

        Returns:
            List[str]: List of expanded address variants.
        """
        variants = list(expand_address(address))[:max_variants]
        return variants if variants else [address]
    
    def __parse_address(self, address: str) -> Dict[str, str]:
        """
        Parse an address string into its components using libpostal.

        Args:
            address (str): Address string.

        Returns:
            Dict[str, str]: Dictionary of parsed address parts.
        """
        parsed = dict(parse_address(address))
        return {k: self.__strip_and_norm(v) for v, k in parsed.items()}
    
    def __canonical_city(self, city: str) -> str:
        """
        Returns the longest variant of the city name after stripping and normalizing.

        Args:
            city (str): City name.

        Returns:
            str: Canonical city name.
        """
        city_clean = self.__strip_and_norm(city)
        city_variants = self.__expand_variants(city_clean)
        best_variant = max(city_variants, key=len)
        return best_variant
    
    def __canonical_country(self, country: str) -> str:
        """
        Returns the longest variant of the country name after stripping and normalizing.

        Args:
            country (str): Country name.

        Returns:
            str: Canonical country name.
        """
        country_clean = self.__strip_and_norm(country)
        country_variants = self.__expand_variants(country_clean)
        best_variant = max(country_variants, key=len)
        return best_variant
    
    def __canonicalise_parts(self, parts: Dict[str, str]) -> Tuple[Dict[str, str], str]:
        """
        Canonicalize address parts and construct a canonical address string.

        Args:
            parts (Dict[str, str]): Dictionary of address parts.

        Returns:
            Tuple[Dict[str, str], str]: (Canonicalized parts, canonical address string)
        """
        ordered_keys = ['house_number', 'road', 'suburb', 'city', 'state', 'postcode', 'country']
        canonical_parts = {key: parts.get(key, '') for key in ordered_keys if parts.get(key)}
        canonical_parts['city'] = self.__canonical_city(canonical_parts.get('city', ''))
        canonical_parts['country'] = self.__canonical_country(canonical_parts.get('country', ''))
        segments = list(canonical_parts.values())
        segments = [s for i,s in enumerate(segments) if s and s not in segments[:i]]
        canonical_address = ', '.join(segments)
        return canonical_parts, canonical_address

    def get_canonical(self, address: str, country_name: str = None) -> Tuple[str, Dict[str, str]]:
        """
        Get the canonical address string and parts for a given address.

        Args:
            address (str): Address string.
            country_name (str, optional): Country name to use if missing.

        Returns:
            Tuple[str, Dict[str, str]]: (Canonical address string, canonical parts dictionary)
        """
        address_clean = self.__strip_and_norm(address)
        address_variants = self.__expand_variants(address_clean)
        best_variant_canonical = None
        best_len = -1
        for variant in address_variants:
            address_parts = self.__parse_address(variant)
            address_parts, address_canonical = self.__canonicalise_parts(address_parts)
            if 'city' in address_parts and 'country' in address_parts:
                if len(address_canonical) > best_len:
                    best_variant_canonical = address_canonical
                    best_len = len(address_canonical)

        if not country_name or country_name.lower() in ('', 'none'):
            if self.geo_config.default_country and self.geo_config.default_country.lower() != 'none':
                country_name = self.geo_config.default_country

        if address_parts.get('country', '') == '' and country_name is not None:
            address_parts['country'] = country_name
            if best_variant_canonical:
                best_variant_canonical = f"{best_variant_canonical}, {address_parts['country']}"
            else:
                best_variant_canonical = address_parts['country']
        return best_variant_canonical, address_parts
    
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
            include_canonical (bool): Whether to include canonical address info.
        """
        self.default_country = default_country
        self.always_geocode = always_geocode
        self.location_cache_file = cache_file

        self.geo_cache = GeoCache(cache_file, always_geocode, alt_place_file_path)
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
                logger.info(f"Geocoded {place} to {location.lat_lon}")

        if location:
            continent = location.continent
            if not continent or continent.strip().lower() in ('', 'none'):
                location.continent = self.geo_config.get_continent_for_country_code(location.country_code)

        return location