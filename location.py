"""
location.py - Location and LatLon classes for GEDCOM mapping.

Provides LatLon for coordinate validation and Location for geocoded place information.
"""

import logging
from typing import Optional, Union

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
        ... (other optional attributes)
    """
    __slots__ = [
        'used', 'lat_lon', 'country_code', 'country_name', 'continent', 'found_country', 'address',
        'name', 'alt', 'country', 'region', 'type', 'class_', 'icon', 'place_id', 'boundry', 'size', 'importance'
    ]
    def __init__(
        self,
        used: int = 0,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        country_code: Optional[str] = None,
        country_name: Optional[str] = None,
        continent: Optional[str] = None,
        found_country: bool = False,
        address: Optional[str] = None,
        name: Optional[str] = None,
        alt: Optional[str] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
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
            else:
                setattr(obj, key, value)
        lat_key = next((k for k in d.keys() if k.lower() in ("latitude", "lat")), None)
        lon_key = next((k for k in d.keys() if k.lower() in ("longitude", "long")), None)
        if lat_key and lon_key:
            obj.lat_lon = LatLon(d[lat_key], d[lon_key])
        obj.used = 0
        return obj