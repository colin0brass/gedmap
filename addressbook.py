"""
addressbook.py - FuzzyAddressBook for GEDCOM mapping.

Provides a class for storing, managing, and fuzzy-matching geocoded addresses.
"""

import logging
from typing import Any, Dict, Optional, Union, List
from rapidfuzz import process, fuzz

from location import LatLon, Location

logger = logging.getLogger(__name__)

class FuzzyAddressBook:
    """
    Stores and manages a collection of geocoded addresses with fuzzy matching support.

    Attributes:
        __addresses (Dict[str, Location]): Internal mapping of address strings to Location objects.
        __alt_addr_to_address_lookup (Dict[str, List[str]]): Maps alt_addr to addresses.
        __canonical_addr_to_address_lookup (Dict[str, List[str]]): Maps canonical_addr to addresses.
        summary_columns (List[str]): List of columns for summary output.
    """

    def __init__(self):
        """
        Initialize an empty FuzzyAddressBook.
        """
        self.__addresses : Dict[str, Location] = {}
        self.__alt_addr_to_address_lookup: Dict[str, List[str]] = {}
        self.__canonical_addr_to_address_lookup: Dict[str, List[str]] = {}
        self.summary_columns = [
            'address', 'alt_addr', 'canonical_addr', 'used', 'type', 'class_', 'icon',
            'latitude', 'longitude', 'found_country', 'country_code', 'country_name'
        ]

    def get_summary_row_dict(self, address: str) -> Dict[str, Any]:
        """
        Get a summary dictionary for a given address.

        Args:
            address (str): The address to summarize.

        Returns:
            Dict[str, Any]: Summary dictionary with keys from self.summary_columns.
        """
        location = self.__addresses.get(address)
        if location is None:
            return {}
        row = {col: getattr(location, col, None) for col in self.summary_columns}
        if location.lat_lon:
            row['latitude'] = location.lat_lon.lat
            row['longitude'] = location.lat_lon.lon
        else:
            row['latitude'] = None
            row['longitude'] = None
        return row
    
    def __add_address(self, key: str, location: Location):
        """
        Add a Location object to the address book and update alt_addr lookup.

        Args:
            key (str): Address string.
            location (Location): Location object to add.
        """
        if location is not None:
            self.__addresses[key] = location
            self.__add_alt_addr_to_address_lookup(location.alt_addr, key)

    def add_address(self, address: str, location: Union[Location, None]):
        """
        Add a new address to the address book, using fuzzy matching to find
        the best existing address if there's a close match, and use same alt_addr.

        Args:
            address (str): The address to add.
            location (Location): The location data associated with the address.
        """
        existing_key = self.fuzzy_lookup_address(address)

        if existing_key is not None:
            # If a similar (or identical) address exists, create or update the entry with the same alt_addr
            existing_location = self.__addresses[existing_key]
            if existing_key == address: # exact match; use existing location and increment usage
                if location is None:
                    logger.warning(f"Exact match found for address '{address}' but no location provided; using existing location.")
                if isinstance(existing_location, Location):
                    location = existing_location.merge(location)
                    location.used = existing_location.used + 1
                if not isinstance(location, Location):
                    location = Location(address=address, used=1)
            # Update the existing entry with the new location data
            self.__add_address(existing_key, location)
        else:
            location = Location(address=address) if location is None else location

            # If no similar address exists, add it as a new entry.
            self.__add_address(address, location)

    def get_address(self, key: str) -> Optional[Location]:
        """
        Retrieve a Location object by address key.

        Args:
            key (str): Address string.

        Returns:
            Optional[Location]: Location object if found, else None.
        """
        return self.__addresses.get(key)

    def __add_alt_addr_to_address_lookup(self, alt_addr: str, address: str):
        """
        Add an address to the alt_addr lookup dictionary.

        Args:
            alt_addr (str): Alternative address string.
            address (str): Address string to associate.
        """
        if alt_addr is not None and alt_addr != '' and alt_addr.lower() != 'none':
            if alt_addr not in self.__alt_addr_to_address_lookup:
                self.__alt_addr_to_address_lookup[alt_addr] = []
            self.__alt_addr_to_address_lookup[alt_addr].append(address)

    def get_address_list_for_alt_addr(self, alt_addr: str) -> List[str]:
        """
        Get a list of addresses associated with a given alt_addr.

        Args:
            alt_addr (str): Alternative address string.

        Returns:
            List[str]: List of associated addresses.
        """
        return self.__alt_addr_to_address_lookup.get(alt_addr, [])

    def get_address_list_for_canonical_addr(self, canonical_addr: str) -> List[str]:
        """
        Get a list of addresses associated with a given canonical_addr.

        Args:
            canonical_addr (str): Canonical address string.

        Returns:
            List[str]: List of associated addresses.
        """
        return self.__canonical_addr_to_address_lookup.get(canonical_addr, [])

    def get_canonical_addr(self, address: str) -> Optional[str]:
        """
        Get the canonical address for a given address.

        Args:
            address (str): Address string.

        Returns:
            Optional[str]: Canonical address if found, else None.
        """
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

    def get_address_list(self) -> List[str]:
        """
        Returns the list of addresses in the address book.

        Returns:
            List[str]: List of addresses.
        """
        return list(self.__addresses.keys())

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
            Optional[str]: The best matching address key, or None if no good match found.
        """
        choices = list(self.__addresses.keys())
        if choices:
            match, score, _ = process.extractOne(address, choices, scorer=fuzz.token_sort_ratio)
            if score >= threshold:
                return match
        return None