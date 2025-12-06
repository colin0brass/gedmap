"""
gedcom_date.py - Date normalization utilities for GEDCOM processing.

Provides the GedcomDate class for parsing, normalizing, and converting GEDCOM date formats using ged4py.
Supports:
    - Normalization of ged4py DateValue to GregorianDate or string
    - Parsing of date phrases, ranges, ordinals, and free-text
    - Extraction of year, month, and day information
    - Range simplification policies ('first', 'last', 'none')

Author: @colin0brass
Last updated: 2025-12-06
"""


import re
from typing import Optional, Union
from ged4py.date import DateValue
from ged4py.calendar import GregorianDate
import logging

logger = logging.getLogger(__name__)

class GedcomDate:
    """
    Utility class for normalizing and parsing GEDCOM date values.

    Wraps ged4py DateValue, GregorianDate, or string date representations and provides normalization to GregorianDate or string for various GEDCOM date formats.
    Handles ranges, phrases, and ordinal/fallback date parsing from free-text. Uses __slots__ for memory optimization.

    Attributes:
        original: The original date value (DateValue, GregorianDate, str, or GedcomDate).
        date: The parsed date value (DateValue, GregorianDate, str, or None).
        simplify_range_policy: Policy for range simplification ('first', 'last', or 'none').
    """
    __slots__ = [
        'original',
        'date',
        'simplify_range_policy'
    ]

    def __init__(self, date: Union[DateValue, str, "GedcomDate", None], simplify_range_policy: str = 'first'):
        """
        Initialize a GedcomDate instance.

        Args:
            date: The original date value (DateValue, GregorianDate, str, GedcomDate, or None).
            simplify_range_policy: Policy for range simplification ('first', 'last', or 'none').
        """
        self.original: Union[DateValue, str, "GedcomDate", None] = date
        self.date = self._parse(date)
        self.simplify_range_policy: str = simplify_range_policy

    @property
    def kind(self):
        """
        Returns the kind of the underlying date value if it is a ged4py.date.DateValue, else None.

        Returns:
            str or None: The kind of the date value, or None if not available.
        """
        if hasattr(self.date, 'kind'):
            return self.date.kind
        return None

    def _parse(self, date: Union[DateValue, str, "GedcomDate", None]) -> Union[DateValue, str, None]:
        """
        Parse the input date into a DateValue, or return the string as is.

        Args:
            date: The input date value (DateValue, str, GedcomDate, or None).

        Returns:
            DateValue, str, or None: Parsed date value or original string.
        """
        if isinstance(date, GedcomDate):
            return date.date
        elif isinstance(date, DateValue) or date is None:
            return date
        elif isinstance(date, str):
            try:
                return DateValue.parse(date)
            except Exception as e:
                logger.warning(f"Failed to parse date string '{date}': {e}")
                return date
        else:
            raise TypeError(f"Unsupported date type: {type(date)}")

    def update(self, date: Optional[Union[DateValue, str, "GedcomDate", None]], simplify_range_policy: Optional[str] = None) -> None:
        """
        Update the GedcomDate instance with a new date value and/or range policy.

        Args:
            date: The new date value (DateValue, str, GedcomDate, or None).
            simplify_range_policy: Optional new range simplification policy.
        """
        if date is not None:
            self.original = date
        if simplify_range_policy is not None:
            self.simplify_range_policy = simplify_range_policy
        self.date = self._parse(self.original)

    @property
    def resolved(self) -> Optional[Union[GregorianDate, str]]:
        """
        Resolve the date to a GregorianDate or string.

        For ranges, returns first or last date based on simplify_range_policy.
        For phrases, parses and resolves the phrase.

        Returns:
            GregorianDate, str, tuple, or None: The resolved date value.
        """
        if not self.date:
            return None
        kind = getattr(self.date, 'kind', None)
        if kind is None:
            return None
        if kind.name in ("RANGE", "PERIOD"):
            date1 = getattr(self.date, 'date1', None)
            date2 = getattr(self.date, 'date2', None)
            if self.simplify_range_policy == "last":
                logger.info(f"Simplifying date range {self.date} to last date: {date2}")
                return date2
            elif self.simplify_range_policy == "first":
                logger.info(f"Simplifying date range {self.date} to first date: {date1}")
                return date1
            else: # none
                return (date1, date2)
        elif kind.name == "PHRASE":
            return self._date_from_phrase()
        else: # SIMPLE, ABOUT, AFTER, BEFORE, etc.
            if isinstance(self.date, str):
                return self._parse_fallback_phrase(self.date)
            else:
                return self.date.date

    @property
    def single(self) -> Optional[Union[GregorianDate, str]]:
        """
        Return a single date representation.

        For ranges, returns first or last date based on simplify_range_policy.
        For phrases, parses and resolves the phrase.

        Returns:
            GregorianDate, str, or None: The single date value.
        """
        date = self.resolved
        if isinstance(date, tuple):
            if self.simplify_range_policy == "last":
                return date[1]
            elif self.simplify_range_policy == "first":
                return date[0]
            else:
                return None
        return date

    @property
    def year_num(self) -> Optional[int]:
        """
        Return the year as an integer, if possible.

        For ranges, returns first or last year based on simplify_range_policy.
        For phrases, attempts to extract year from phrase.

        Returns:
            int or None: The year value, or None if not found.
        """
        single_date = self.single
        if hasattr(single_date, 'year'):
            year = getattr(single_date, 'year', None)
            return int(year) if year is not None else None
        else:
            match = re.search(r'(-?\d{3,4})', str(single_date))
            if match:
                return int(match.group(1))
            else:
                logger.warning('GedcomDate: year_num: unable to parse single date: "%s"', single_date)
                return None

    @property
    def year_str(self) -> Optional[str]:
        """
        Return the year as a string, if possible.

        Returns:
            str or None: The year as a string, or None if not found.
        """
        year = self.year_num
        return str(year) if year is not None else None

    def _date_from_phrase(self) -> Optional[Union[GregorianDate, str, tuple]]:
        """
        Extract and normalize a date from a GEDCOM date phrase.

        Returns a GregorianDate if possible, else the best string representation.
        Supports ranges like 'BET JUL AND SEP 1913' and single dates.
        For ranges, returns a tuple (start, end) of GregorianDate objects.

        Returns:
            GregorianDate, str, tuple, or None: The normalized date value.
        """
        phrase = getattr(self.date, 'phrase', None)
        if not phrase:
            logger.warning('GedcomDate: _date_from_phrase: no phrase available on date.value')
            return None
        
        if phrase is None or not isinstance(phrase, str):
            return None

        result = self._parse_range_phrase(phrase)
        if result is not None:
            return result

        result = self._parse_ordinal_phrase(phrase)
        if result is not None:
            return result

        result = self._parse_fallback_phrase(phrase)
        return result

    def _parse_range_phrase(self, phrase: str) -> Optional[tuple]:
        """
        Parse a GEDCOM range phrase (e.g., 'BET JUL AND SEP 1913') and return a tuple of GregorianDate objects.

        Args:
            phrase (str): GEDCOM date phrase representing a range.

        Returns:
            tuple or None: Tuple of GregorianDate objects (start, end) or None if not matched.
        """
        range_re = re.compile(r'BET\s+([A-Z]{3,9})\s+AND\s+([A-Z]{3,9})\s+(\d{3,4})', re.I)
        m = range_re.match(phrase.strip())
        if m:
            month1, month2, year = m.groups()
            year = int(year)
            month1_str = month1.upper()[:3]
            month2_str = month2.upper()[:3]
            start = GregorianDate(year=year, month=month1_str)
            end = GregorianDate(year=year, month=month2_str)
            return (start, end)
        return None

    def _parse_ordinal_phrase(self, phrase: str) -> Optional[GregorianDate]:
        """
        Parse an ordinal date phrase (e.g., '15 JUL 1913') and return a GregorianDate object.

        Args:
            phrase (str): GEDCOM date phrase representing an ordinal date.

        Returns:
            GregorianDate or None: GregorianDate object or None if not matched.
        """
        ordinal_date_re = re.compile(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(\d{4})')
        m = ordinal_date_re.match(phrase.strip())
        if m:
            day, month, year = m.groups()
            return GregorianDate(year=int(year), month=month.upper()[:3], day=int(day))
        return None

    def _parse_fallback_phrase(self, phrase: str) -> Optional[Union[GregorianDate, str]]:
        """
        Parse a fallback date phrase and return a GregorianDate or string if possible.

        Handles cases like 'Spring 1913', '1913', or partial dates.

        Args:
            phrase (str): Free-text GEDCOM date phrase.

        Returns:
            GregorianDate, str, or None: Parsed date value or original phrase.
        """
        YEAR_RE = re.compile(r'(?<!\d)(-?\d{3,4})(?!\d)')
        MONTH_RE = re.compile(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|JUNE|JULY|SEPTEMBER|OCTOBER|DECEMBER|AUGUST|NOVEMBER|MARCH|FEBRUARY|MAY|APRIL)', re.I)
        DAY_RE = re.compile(r'(?<!\d)(\d{1,2})(?=\s+[A-Z]{3,9})')

        if not phrase or not isinstance(phrase, str):
            return None

        year_match = YEAR_RE.search(phrase)
        year = int(year_match.group(1)) if year_match else None

        month_match = MONTH_RE.search(phrase)
        month = month_match.group(1) if month_match else None
        month_str = month.upper()[:3] if month else None

        day_match = DAY_RE.search(phrase)
        day = int(day_match.group(1)) if day_match else None

        if year:
            return GregorianDate(year=year, month=month_str, day=day)
        if month or day:
            parts = []
            if day:
                parts.append(str(day))
            if month:
                parts.append(month)
            return " ".join(parts)
        return phrase
