"""
person.py - geo_gedcom person and individual modeling for GEDCOM data.

This module provides the Person class and utilities for modeling individuals
in GEDCOM genealogical data. It supports:
    - Parsing person records
    - Extracting and normalizing personal attributes
    - Associating people with life events and relationships

Module: geo_gedcom.person
Authors: @lmallez, @D-jeffrey, @colin0brass
Last updated: 2025-12-06
"""

__all__ = ['Person']

import logging
import re
from typing import Dict, Union, Optional, List

from ged4py.model import Record, NameRec
from ged4py.date import DateValue
from .lat_lon import LatLon
from .location import Location
from .gedcom_date import GedcomDate
from .partner import Partner
from .life_event import LifeEvent

logger = logging.getLogger(__name__)

class Person:
    """
    Represents a person in the GEDCOM file.

    Attributes:
        xref_id (str): GEDCOM cross-reference ID.
        name (Optional[str]): Full name.
        firstname (Optional[str]): First name.
        surname (Optional[str]): Surname.
        maidenname (Optional[str]): Maiden name.
        sex (Optional[str]): Sex ('M', 'F', or None).
        title (Optional[str]): Title.
        birth (LifeEvent): Birth event.
        death (LifeEvent): Death event.
        baptism (List[LifeEvent]): Baptism events.
        marriages (List[LifeEvent]): Marriage events.
        residences (List[LifeEvent]): Residence events.
        military (List[LifeEvent]): Military service events.
        arrivals (List[LifeEvent]): Arrival events.
        departures (List[LifeEvent]): Departure events.
        father (Person): Father (xref ID or Person).
        mother (Person): Mother (xref ID or Person).
        children (List[str]): List of children xref IDs.
        partners (List[str]): List of partner xref IDs.
        age (Optional[Union[int, str]]): Age or age with cause of death.
        photos_all (List[str]): All photo file paths or URLs.
        photo (Optional[str]): Primary photo file path or URL.
        location (Optional[Location]): Best known location (may be None).
        latlon (LatLon): Latitude/longitude (best known position).
        family_spouse (List[str]): FAMS family IDs (as spouse/partner).
        family_child (List[str]): FAMC family IDs (as child).
    """
    __slots__ = ['xref_id',
                 'name', 'firstname', 'surname', 'maidenname',
                 'sex','title',
                 'birth', 'death',
                 'baptism', 'marriages', 'residences', 'military',
                 'arrivals', 'departures',
                 'father', 'mother', 'children', 'partners', 
                 'age', 'photos_all', 'photo', 
                 'location', 'latlon', 
                 'family_spouse', 'family_child']
    def __init__(self, xref_id : str):
        """
        Initialize a Person instance with all relationship, event, and metadata fields.

        Args:
            xref_id (str): GEDCOM cross-reference ID.
        """
        self.xref_id = xref_id

        self.name : Optional[str] = None
        self.firstname : Optional[str] = None
        self.surname : Optional[str] = None
        self.maidenname : Optional[str] = None

        self.sex : Optional[str] = None
        self.title : Optional[str] = None

        self.birth : LifeEvent = None
        self.death : LifeEvent = None

        self.baptism : List[LifeEvent] = []
        self.marriages : List[LifeEvent] = []
        self.residences : List[LifeEvent] = []
        self.military : List[LifeEvent] = []

        self.arrivals : List[LifeEvent] = []
        self.departures : List[LifeEvent] = []

        self.father : Person = None
        self.mother : Person = None
        
        self.children : List[str] = []
        self.partners : List[str] = []

        self.age = None           # This can be age number or including the cause of death
        self.photos_all = []         # URL or file path to photos
        self.photo : Optional[str] = None        # URL or file path to primary photo

        self.location = None
        self.latlon : LatLon = None

        self.family_spouse = []
        self.family_child = []

    def __str__(self) -> str:
        """
        Returns a string representation of the person (xref and name).
        """
        return f"Person(id={self.xref_id}, name={self.name})"

    def __repr__(self) -> str:
        """
        Returns a detailed string representation of the person for debugging.
        """
        return f"[ {self.xref_id} : {self.name} - {self.father} & {self.mother} - {self.latlon} ]"

    def ref_year(self) -> str:
        """
        Returns a reference year string for the person.

        Returns:
            str: Reference year string.
        """
        if self.birth and self.birth.date:
            year = self.birth.date.year_str
            return f'Born {year}' if year else 'Born Unknown'
        if self.death and self.death.date:
            year = self.death.date.year_str
            return f'Died {year}' if year else 'Died Unknown'
        return 'Unknown'
    
    def bestlocation(self):
        """
        Returns the best known location for the person as [latlon, description].
        """
        best = ["Unknown", ""]
        if self.birth and self.birth.location:
            best = [
                str(self.birth.location.latlon),
                f"{self.birth.place} (Born)" if self.birth.place else "",
            ]
        elif self.death and self.death.location:
            best = [
                str(self.death.location.latlon),
                f"{self.death.place} (Died)" if self.death.place else "",
            ]
        return best

    def bestLatLon(self):
        """
        Returns the best known LatLon for the person (birth, then death, else None).
        """
        best = LatLon(None, None)
        if self.birth and self.birth.latlon and self.birth.latlon.hasLocation():
            best = self.birth.latlon
        elif self.death and self.death.latlon and self.death.latlon.hasLocation():
            best = self.death.latlon
        return best
    
