import logging

from pathlib import Path
from typing import Dict, List, Optional

from .gedcom import Gedcom
from .geocode import Geocode
from .location import Location
from .addressbook import FuzzyAddressBook
from .life_event import LifeEvent
from .lat_lon import LatLon

logger = logging.getLogger(__name__)

class GeolocatedGedcom(Gedcom):
    """
    GEDCOM handler with geolocation support.

    Attributes:
        geocoder (Geocode): Geocode instance.
        address_book (FuzzyAddressBook): Address book of places.
    """
    __slots__ = [
        'geocoder',
        'address_book',
        'alt_place_file_path',
        'geo_config_path'
    ]
    geolocate_all_logger_interval = 20
    
    def __init__(
            self,
            gedcom_file: Path,
            location_cache_file: Path,
            default_country: Optional[str] = None,
            always_geocode: Optional[bool] = False,
            alt_place_file_path: Optional[Path] = None,
            geo_config_path: Optional[Path] = None,
            file_geo_cache_path: Optional[Path] = None,
            include_canonical: bool = True
    ):
        """
        Initialize GeolocatedGedcom.

        Args:
            gedcom_file (str): Path to GEDCOM file.
            location_cache_file (str): Location cache file.
            default_country (Optional[str]): Default country for geocoding.
            always_geocode (Optional[bool]): Whether to always geocode.
            alt_place_file_path (Optional[Path]): Path to alternative place file.
            geo_config_path (Optional[Path]): Path to geographic configuration file.
            file_geo_cache_path (Optional[Path]): Path to per-file geo cache.
            include_canonical (bool): Whether to include canonical addresses.
        """
        super().__init__(gedcom_file)

        self.address_book = FuzzyAddressBook()

        self.geocoder = Geocode(
            cache_file=location_cache_file,
            default_country=default_country,
            always_geocode=always_geocode,
            alt_place_file_path=alt_place_file_path if alt_place_file_path else None,
            geo_config_path=geo_config_path if geo_config_path else None,
            file_geo_cache_path=file_geo_cache_path,
            include_canonical=include_canonical
        )

        self.read_full_address_book()
        self.geolocate_all()
        self.parse_people()

    def save_location_cache(self) -> None:
        """
        Save the location cache to the specified file.
        """
        self.geocoder.save_geo_cache()

    def geolocate_all(self) -> None:
        """
        Geolocate all places in the GEDCOM file.
        """
        cached_places, non_cached_places = self.geocoder.separate_cached_locations(self.address_book)
        logger.info(f"Found {cached_places.len()} cached places, {non_cached_places.len()} non-cached places.")

        logger.info(f"Geolocating {cached_places.len()} cached places...")
        for place, data in cached_places.addresses().items():
            use_place = data.alt_addr if data.alt_addr else place
            location = self.geocoder.lookup_location(use_place)
            self.address_book.add_address(place, location)
        num_non_cached_places = non_cached_places.len()

        logger.info(f"Geolocating {num_non_cached_places} non-cached places...")
        for place in non_cached_places.addresses().keys():
            logger.info(f"- {place}...")
        for idx, (place, data) in enumerate(non_cached_places.addresses().items(), 1):
            use_place = data.alt_addr if data.alt_addr else place
            location = self.geocoder.lookup_location(use_place)
            self.address_book.add_address(place, location)
            if idx % self.geolocate_all_logger_interval == 0 or idx == num_non_cached_places:
                logger.info(f"Geolocated {idx} of {num_non_cached_places} non-cached places...")
                
        logger.info(f"Geolocation of all {self.address_book.len()} places completed.")

    def parse_people(self) -> None:
        """
        Parse and geolocate all people in the GEDCOM file.
        """
        super()._parse_people()
        self.geolocate_people()

    # def get_full_address_book(self) -> FuzzyAddressBook:
    #     """
    #     Get all places from the GEDCOM file.

    #     Returns:
    #         FuzzyAddressBook: Address book of places.
    #     """
    #     self.address_book = self.gedcom_parser.get_full_address_book()
    #     return self.address_book

    def read_full_address_book(self) -> None:
        """
        Get all places from the GEDCOM file.
        """
        super().read_full_address_list()
        for place in self.address_list:
            if not self.address_book.get_address(place):
                # location = self.geocoder.lookup_location(place)
                location = None
                self.address_book.add_address(place, location)

    def geolocate_people(self) -> None:
        """
        Geolocate birth, marriage, and death events for all people.
        """
        for person in self.people.values():
            found_location = False
            if person.birth:
                event = self.__geolocate_event(person.birth)
                person.birth.location = event.location
                if not found_location and event.location and event.location.latlon and event.location.latlon.is_valid():
                    person.latlon = event.location.latlon
                    found_location = True
            for marriage_event in person.marriages:
                event = self.__geolocate_event(marriage_event)
                marriage_event.location = event.location
                if not found_location and event.location and event.location.latlon and event.location.latlon.is_valid():
                    person.latlon = event.location.latlon
                    found_location = True
            if person.death:
                event = self.__geolocate_event(person.death)
                person.death.location = event.location
                if not found_location and event.location and event.location.latlon and event.location.latlon.is_valid():
                    person.latlon = event.location.latlon
                    found_location = True

    def __geolocate_event(self, event: LifeEvent) -> LifeEvent:
        """
        Geolocate a single event. If no location is found, event.location remains None.

        Args:
            event (LifeEvent): The event to geolocate.

        Returns:
            LifeEvent: The event with updated location and latlon if found.
        """
        record = getattr(event, 'record', None)
        if record:
            place_tag = record.sub_tag('PLAC')
            if place_tag:
                map_tag = place_tag.sub_tag('MAP')
                if place_tag.value:
                    location = self.geocoder.lookup_location(place_tag.value)
                    event.location = location
                if map_tag:
                    lat = map_tag.sub_tag('LATI')
                    lon = map_tag.sub_tag('LONG')
                    if lat and lon:
                        latlon = LatLon(lat.value, lon.value)
                        event.latlon = latlon if latlon.is_valid() else None
                    else:
                        event.latlon = None
            else:
                logger.info(f"No place tag found for event in record {record}")
        else:
            logger.warning("No record found for event")
        return event
