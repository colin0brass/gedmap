"""
life_event.py - geo_gedcom life event extraction and modeling for GEDCOM data.

This module provides the LifeEvent class and utilities for extracting and modeling
life events (birth, death, marriage, etc.) from GEDCOM data. It supports:
    - Parsing event records
    - Normalizing event dates and locations
    - Associating events with people and families

Module: geo_gedcom.life_event
Author: @colin0brass
Last updated: 2025-12-06
"""

from typing import Optional
from ged4py.model import Record
from ged4py.date import DateValue
from .gedcom_date import GedcomDate
from .lat_lon import LatLon
from .location import Location

class LifeEvent:
    """
    Represents a life event (birth, death, marriage, etc.) for a person.

    Attributes:
        place (Optional[str]): The place where the event occurred.
        date (GedcomDate): The date of the event (resolved GEDCOM date).
        what (Optional[str]): The type of event (e.g., 'BIRT', 'DEAT').
        record (Optional[Record]): The GEDCOM record associated with the event.
        location (Optional[Location]): Geocoded location object.
    """
    __slots__ = [
        'place',
        'date',
        'what',
        'record',
        'location'
    ]
    def __init__(self, place: str, date: DateValue = None, position: Optional[LatLon] = None, what: str = '', record=None):
        """
        Initialize a LifeEvent instance.

        Args:
            place (str): Place of the event.
            date (str or DateValue): Date of the event (will be parsed and resolved using GedcomDate).
            position (Optional[LatLon]): Latitude/longitude.
            what (Optional[str]): Type of event (e.g., 'BIRT', 'DEAT').
            record (Optional[Record]): GEDCOM record.
        """
        self.place: str = place
        self.date: GedcomDate = GedcomDate(date)
        self.what: str = what
        self.record: Optional[Record] = record
        self.location: Location = Location(position=position, address=place) if position or place else None

    def __repr__(self) -> str:
        """
        Returns a string representation of the LifeEvent for debugging.
        """
        if self.what:
            return f"[ {str(self.date)} : {self.place} is {self.what}]"
        return f'[ {str(self.date)} : {self.place} ]'

    @property
    def event_str(self):
        """
        Returns a string describing the event (date and place).
        """
        place = f" at {self.getattr('place')}" if self.place is not None else ""
        date_str = ""
        if self.date:
            date_str = self.date.year_str
        date = f" on {date_str}" if date_str else ""
        return f"{date}{place}"

    def getattr(self, attr):
        """
        Returns the value of a named attribute for the event, with some aliases.
        """
        if attr == 'latlon':
            return self.location.latlon if self.location else None
        elif attr == 'when' or attr == 'date':
            return self.date.resolved if self.date else None
        elif attr == 'where' or attr == 'place':
            return self.place if self.place else None
        elif attr == 'what':
            return self.what if self.what else ""
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("LifeEvent attr: %s' object has no attribute '%s'", type(self).__name__, attr)
        return None

    def __str__(self) -> str:
        """
        Returns a string summary of the event (place, date, latlon, what).
        """
        return f"{self.getattr('place')} : {self.getattr('date')} - {self.getattr('latlon')} {self.getattr('what')}"
