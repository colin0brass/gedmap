"""
location.py - Location and LatLon classes for GEDCOM mapping.

Provides LatLon for coordinate validation and Location for geocoded place information.
"""

import logging
from typing import Any, Dict, Optional, Union, List
from rapidfuzz import process, fuzz

from location import LatLon, Location

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)

class FuzzyAddressBook:
    def __init__(self):
        self.__addresses : Dict[str, Location] = {}
        self.__alt_addr_to_address_lookup: Dict[str, List[str]] = {}
        self.__canonical_addr_to_address_lookup: Dict[str, List[str]] = {}

    def __add_address(self, key: str, location: Location):
        if location is not None:
            self.__addresses[key] = location
            self.__add_alt_addr_to_address_lookup(location.alt_addr, key)

    def get_address(self, key: str) -> Optional[Location]:
        return self.__addresses.get(key)

    def __add_alt_addr_to_address_lookup(self, alt_addr: str, address: str):
        if alt_addr and alt_addr.lower() != 'none':
            if alt_addr not in self.__alt_addr_to_address_lookup:
                self.__alt_addr_to_address_lookup[alt_addr] = []
            self.__alt_addr_to_address_lookup[alt_addr].append(address)

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

        if existing_key is not None:
            # If a similar (or identical) address exists, create or update the entry with the same alt_addr
            existing_location = self.__addresses[existing_key]
            canonical_addr = existing_location.canonical_addr
            if existing_key == address: # exact match; use existing location and increment usage
                location = location.merge(existing_location)
                location.used = existing_location.used + 1
            # Update the existing entry with the new location data
            self.__add_address(existing_key, location)
        else:
            location = Location(address=address) if location is None else location

            # If no similar address exists, add it as a new entry.
            self.__add_address(address, location)