"""
location.py - Location and LatLon classes for GEDCOM mapping.

Provides LatLon for coordinate validation and Location for geocoded place information.
"""

import logging
import re
from typing import Dict, Optional, Union, List
from rapidfuzz import process, fuzz
from postal.expand import expand_address
from postal.parser import parse_address
from unidecode import unidecode

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)

class LatLon:
    """
    Represents a latitude/longitude pair.
    Converts N/S/E/W prefixed strings to signed floats.

    Attributes:
        lat (Optional[float]): Latitude value.
        lon (Optional[float]): Longitude value.
    """

    __slots__ = ['lat', 'lon']

    def __init__(self, lat: Union[str, float, None], lon: Union[str, float, None]):
        """
        Initialize LatLon with latitude and longitude.

        Args:
            lat (str|float|None): Latitude value or string.
            lon (str|float|None): Longitude value or string.
        """
        self.lat = self._parse_lat(lat)
        self.lon = self._parse_lon(lon)

    @staticmethod
    def _parse_lat(lat: Union[str, float, None]) -> Optional[float]:
        """
        Parse latitude from string or float, handling N/S prefixes.

        Args:
            lat (str|float|None): Latitude value or string.

        Returns:
            Optional[float]: Parsed latitude or None.
        """
        if lat is None:
            return None
        if isinstance(lat, (float, int)):
            return float(lat)
        lat_str = str(lat).strip()
        if not lat_str:
            return None
        direction = lat_str[0].upper()
        if direction in ('N', 'S'):
            try:
                lat_val = float(lat_str[1:])
                return lat_val if direction == 'N' else -lat_val
            except ValueError:
                return None
        try:
            return float(lat_str)
        except ValueError:
            return None

    @staticmethod
    def _parse_lon(lon: Union[str, float, None]) -> Optional[float]:
        """
        Parse longitude from string or float, handling E/W prefixes.

        Args:
            lon (str|float|None): Longitude value or string.

        Returns:
            Optional[float]: Parsed longitude or None.
        """
        if lon is None:
            return None
        if isinstance(lon, (float, int)):
            return float(lon)
        lon_str = str(lon).strip()
        if not lon_str:
            return None
        direction = lon_str[0].upper()
        if direction in ('E', 'W'):
            try:
                lon_val = float(lon_str[1:])
                return lon_val if direction == 'E' else -lon_val
            except ValueError:
                return None
        try:
            return float(lon_str)
        except ValueError:
            return None

    def is_valid(self) -> bool:
        """
        Return True if both latitude and longitude are not None.

        Returns:
            bool: True if valid, False otherwise.
        """
        return self.lat is not None and self.lon is not None

    def __repr__(self) -> str:
        """
        String representation for debugging.

        Returns:
            str: Representation of LatLon.
        """
        return f"[{self.lat},{self.lon}]"

    def __str__(self) -> str:
        """
        User-friendly string representation.

        Returns:
            str: String representation of LatLon.
        """
        return f"[{self.lat},{self.lon}]"

    @property
    def latitude(self) -> Optional[float]:
        """
        Returns the latitude value.

        Returns:
            Optional[float]: Latitude.
        """
        return self.lat

    @property
    def longitude(self) -> Optional[float]:
        """
        Returns the longitude value.

        Returns:
            Optional[float]: Longitude.
        """
        return self.lon

    @classmethod
    def from_string(cls, s: str) -> "LatLon":
        """
        Create LatLon from a string like 'N51.5,E0.1' or '51.5,0.1'.

        Args:
            s (str): String representation.

        Returns:
            LatLon: Parsed LatLon object.
        """
        parts = s.split(',')
        if len(parts) == 2:
            return cls(parts[0], parts[1])
        return cls(None, None)


class Location:
    """
    Stores geocoded location information.

    Attributes:
        used (int): Usage count.
        lat_lon (LatLon): Latitude/longitude.
        country_code (str): Country code.
        country_name (str): Country name.
        continent (str): Continent name.
        found_country (bool): Whether country was found.
        address (str): Address string.
        alt_addr (str): Alternative address string.
        canonical_addr (str): Canonical address.
        ... (other optional attributes)
    """

    SPACE_RE = re.compile(r"\s+")
    PUNC_RE = re.compile(r"[\,;]+")

    __slots__ = [
        'used', 'lat_lon', 'country_code', 'country_name', 'continent', 'found_country', 'address',
        'alt_addr', 'canonical_addr', 'canonical_parts', 'type', 'class_', 'icon', 'place_id', 'boundry', 'size', 'importance'
    ]
    def __init__(
        self,
        used: int = 0,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        country_code: Optional[str] = None,
        country_name: Optional[str] = None,
        continent: Optional[str] = None,
        found_country: Optional[bool] = False,
        address: Optional[str] = None,
        alt_addr: Optional[str] = None,
        canonical_addr: Optional[str] = None,
        canonical_parts: Optional[Dict[str, str]] = None,
        type: Optional[str] = None,
        class_: Optional[str] = None,
        icon: Optional[str] = None,
        place_id: Optional[str] = None,
        boundry: Optional[str] = None,
        size: Optional[str] = None,
        importance: Optional[str] = None
    ):
        """
        Initialize a Location object with geocoded information.
        """
        self.used = used
        self.lat_lon = LatLon(latitude, longitude) if (latitude is not None and longitude is not None) else None
        self.country_code = country_code
        self.country_name = country_name
        self.continent = continent
        self.found_country = found_country
        self.address = address
        self.alt_addr = alt_addr
        self.canonical_addr = canonical_addr
        self.canonical_parts = {}
        self.type = type
        self.class_ = class_
        self.icon = icon
        self.place_id = place_id
        self.boundry = boundry
        self.size = size
        self.importance = importance

        self.add_canonical(use_alt_addr=True)

    @classmethod
    def from_dict(cls, d: dict) -> "Location":
        """
        Create a Location object from a dictionary.

        Args:
            d (dict): Dictionary of location attributes.

        Returns:
            Location: Location instance.
        """
        obj = cls()
        for key, value in d.items():
            if key.lower() == 'class':
                setattr(obj, 'class_', value)
            elif key.lower() in ('latitude', 'longitude'):
                continue
            elif key.lower() == 'place':
                setattr(obj, 'address', value)
            elif key.lower() == 'alt_place':
                setattr(obj, 'alt_addr', value)
            else:
                setattr(obj, key, value)
        lat_key = next((k for k in d.keys() if k.lower() in ("latitude", "lat")), None)
        lon_key = next((k for k in d.keys() if k.lower() in ("longitude", "long")), None)
        if lat_key and lon_key:
            obj.lat_lon = LatLon(d[lat_key], d[lon_key])
        obj.used = 0
        return obj
    
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

    def add_canonical(self, use_alt_addr: bool = True) -> str:
        use_addr = self.alt_addr if use_alt_addr and self.alt_addr else self.address
        address_clean = self.__strip_and_norm(use_addr)
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
        self.canonical_addr = best_variant_canonical if best_variant_canonical else address_clean
        self.canonical_parts = address_parts if best_variant_canonical else {}


class FuzzyAddressBook:
    def __init__(self):
        self.__addresses : Dict[str, Location] = {}
        self.__alt_addr_to_address_lookup: Dict[str, List[str]] = {}
        self.__canonical_addr_to_address_lookup: Dict[str, List[str]] = {}

    def __add_address(self, key: str, location: Location):
        self.__addresses[key] = location
        self.__add_alt_addr_to_address_lookup(location.alt_addr, key)

        if location.canonical_addr:
            self.__add_canonical_addr_to_address_lookup(location.canonical_addr, key)

    def get_address(self, key: str) -> Optional[Location]:
        return self.__addresses.get(key)

    def __add_alt_addr_to_address_lookup(self, alt_addr: str, address: str):
        if alt_addr and alt_addr.lower() != 'none':
            if alt_addr not in self.__alt_addr_to_address_lookup:
                self.__alt_addr_to_address_lookup[alt_addr] = []
            self.__alt_addr_to_address_lookup[alt_addr].append(address)

    def __add_canonical_addr_to_address_lookup(self, canonical_addr: str, address: str):
        if canonical_addr and canonical_addr.lower() != 'none':
            if canonical_addr not in self.__canonical_addr_to_address_lookup:
                self.__canonical_addr_to_address_lookup[canonical_addr] = []
            self.__canonical_addr_to_address_lookup[canonical_addr].append(address)

    def get_address_list_for_alt_addr(self, alt_addr: str) -> List[str]:
        return self.__alt_addr_to_address_lookup.get(alt_addr, [])

    def get_address_list_for_canonical_addr(self, canonical_addr: str) -> List[str]:
        return self.__canonical_addr_to_address_lookup.get(canonical_addr, [])

    def get_canonical_addr(self, address: str) -> Optional[str]:
        for canonical, addresses in self.__canonical_addr_to_address_lookup.items():
            if address in addresses:
                return canonical
        return None

    def addresses(self) -> Dict[str, Location]:
        """
        Returns the addresses in the address book.

        Returns:
            Dict[str, Location]: Dictionary of addresses.
        """
        return self.__addresses
    
    def get_alt_addr_list(self) -> List[str]:
        """
        Returns the list of alternative addresses in the address book.

        Returns:
            List[str]: List of alternative addresses.
        """
        return list(self.__alt_addr_to_address_lookup.keys())

    def len(self) -> int:
        """
        Returns the number of addresses in the address book.

        Returns:
            int: Number of addresses.
        """
        return len(self.__addresses)

    def fuzzy_lookup_address(self, address: str, threshold: int = 90) -> Optional[str]:
        """
        Find the best fuzzy match for an address in the address book.

        Args:
            address (str): The address to match.
            threshold (int): Minimum similarity score (0-100) to accept a match.

        Returns:
            str: The best matching address key, or None if no good match found.
        """
        choices = list(self.__addresses.keys())
        if choices:
            match, score, _ = process.extractOne(address, choices, scorer=fuzz.token_sort_ratio)
            if score >= threshold:
                return match
        return None

    def add_address(self, address: str, location: Union[Location, None]):
        """
        Add a new address to the address book, using fuzzy matching to find
        the best existing address if there's a close match, and use same alt_addr.

        Args:
            address (str): The address to add.
            location (Location): The location data associated with the address.
        """
        existing_key = self.fuzzy_lookup_address(address)
        existing_location = None

        if existing_key is not None:
            # If a similar (or identical) address exists, create or update the entry with the same alt_addr
            existing_location = self.__addresses[existing_key]
            alt_addr = existing_location.alt_addr
            canonical_addr = existing_location.canonical_addr
            if existing_key == address: # exact match; use existing location and increment usage
                location = existing_location if location is None else location
                location.used = existing_location.used + 1
            if alt_addr is not None:
                location.alt_addr = alt_addr
                location.add_canonical(use_alt_addr=True)
            if canonical_addr is not None and not location.canonical_addr:
                location.canonical_addr = canonical_addr
            # Update the existing entry with the new location data
            self.__add_address(existing_key, location)
        else:
            location = Location(address=address) if location is None else location

            # If no similar address exists, add it as a new entry.
            self.__add_address(address, location)