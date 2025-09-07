"""
location.py - Location and LatLon classes for GEDCOM mapping.

Provides LatLon for coordinate validation and Location for geocoded place information.
"""

import logging
import re
from typing import Dict, Optional, Union

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
            Optional[float]: Parsed latitude or None if invalid.
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
            Optional[float]: Parsed longitude or None if invalid.
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
        Check if both latitude and longitude are not None.

        Returns:
            bool: True if both latitude and longitude are valid, False otherwise.
        """
        return self.lat is not None and self.lon is not None

    def __repr__(self) -> str:
        """
        Return a string representation for debugging.

        Returns:
            str: Representation of LatLon.
        """
        return f"[{self.lat},{self.lon}]"

    def __str__(self) -> str:
        """
        Return a user-friendly string representation.

        Returns:
            str: String representation of LatLon.
        """
        return f"[{self.lat},{self.lon}]"

    @property
    def latitude(self) -> Optional[float]:
        """
        Get the latitude value.

        Returns:
            Optional[float]: Latitude.
        """
        return self.lat

    @property
    def longitude(self) -> Optional[float]:
        """
        Get the longitude value.

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
            LatLon: Parsed LatLon object, or LatLon(None, None) if invalid.
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
        canonical_parts (dict): Canonical address parts.
        type (str): Location type.
        class_ (str): Class type.
        icon (str): Icon name.
        place_id (str): Place identifier.
        boundry (str): Boundary info.
        size (str): Size info.
        importance (str): Importance score.
    """

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

        Args:
            used (int): Usage count.
            latitude (float|None): Latitude value.
            longitude (float|None): Longitude value.
            country_code (str|None): Country code.
            country_name (str|None): Country name.
            continent (str|None): Continent name.
            found_country (bool|None): Whether country was found.
            address (str|None): Address string.
            alt_addr (str|None): Alternative address string.
            canonical_addr (str|None): Canonical address.
            canonical_parts (dict|None): Canonical address parts.
            type (str|None): Location type.
            class_ (str|None): Class type.
            icon (str|None): Icon name.
            place_id (str|None): Place identifier.
            boundry (str|None): Boundary info.
            size (str|None): Size info.
            importance (str|None): Importance score.
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
        self.canonical_parts = canonical_parts
        self.type = type
        self.class_ = class_
        self.icon = icon
        self.place_id = place_id
        self.boundry = boundry
        self.size = size
        self.importance = importance

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
    
    def copy(self) -> "Location":
        """
        Create a copy of this Location.

        Returns:
            Location: A new Location instance with the same attributes.
        """
        new_obj = Location()
        for slot in self.__slots__:
            value = getattr(self, slot)
            # For canonical_parts, make a copy if it's a dict
            if slot == "canonical_parts" and value is not None:
                value = value.copy()
            setattr(new_obj, slot, value)
        return new_obj
    
    def merge(self, other: "Location") -> "Location":
        """
        Merge another Location into this one, preferring non-empty values.

        Args:
            other (Location): Other Location to merge.

        Returns:
            Location: Merged Location instance.
        """
        merged = self.copy()
        if not isinstance(other, Location):
            return merged
        for slot in self.__slots__:
            if slot == 'lat_lon':
                if merged.lat_lon is None and other.lat_lon is not None:
                    merged.lat_lon = other.lat_lon
            else:
                if not getattr(merged, slot) and getattr(other, slot):
                    setattr(merged, slot, getattr(other, slot))
        return merged