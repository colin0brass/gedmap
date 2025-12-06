"""
gedcom.py - Main geo_gedcom data model and handler.

This module defines the Gedcom class, which provides high-level operations for parsing,
filtering, and exporting GEDCOM genealogical data. It supports:
    - Loading and parsing GEDCOM files
    - Filtering ancestors and descendants by generation
    - Searching for people by name
    - Exporting filtered people and associated photos to new GEDCOM files
    - Integrating with geolocation and address book utilities

Module: geo_gedcom.gedcom
Author: @colin0brass
Last updated: 2025-11-29
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple

from .addressbook import FuzzyAddressBook
from .gedcom_parser import GedcomParser
from .person import Person

logger = logging.getLogger(__name__)

class GenerationTracker:
    """
    Tracks people and their generations for ancestor/descendant filtering.

    Stores (person_id, generation) pairs and provides utilities for lookup and grouping.

    Attributes:
        people_gen (List[Tuple[str, int]]): List of (person_id, generation) pairs.
        earliest_generation (int): Earliest generation found.
        latest_generation (int): Latest generation found.
    """
    def __init__(self):
        self.people_gen: List[Tuple[str, int]] = []
        self.earliest_generation = 0
        self.latest_generation = 0

    def add(self, person_id: str, generation: int):
        self.people_gen.append((person_id, generation))
        if generation < self.earliest_generation:
            self.earliest_generation = generation
        if generation > self.latest_generation:
            self.latest_generation = generation

    @property
    def num_generations(self) -> int:
        return self.latest_generation - self.earliest_generation + 1

    def get_generation(self, generation: int) -> List[str]:
        return [pid for pid, gen in self.people_gen if gen == generation]

    def exists(self, person_id: str) -> bool:
        return any(pid == person_id for pid, _ in self.people_gen)

    def all(self) -> Dict[str, int]:
        """Return a dict mapping person_id to generation for all unique person_ids."""
        result = {}
        for pid, gen in self.people_gen:
            if pid not in result:
                result[pid] = gen
        return result

class Gedcom:
    """
    Main GEDCOM handler for people and places.

    Provides high-level operations for parsing, filtering, and exporting GEDCOM genealogical data.

    Attributes:
        gedcom_parser (GedcomParser): Instance for parsing GEDCOM files and extracting data.
        people (Dict[str, Person]): Dictionary of all Person objects indexed by xref_id.
        address_book (FuzzyAddressBook): Address book of all places found in the GEDCOM file.
    """
    __slots__ = [
        'gedcom_parser',
        'people',
        # 'address_book',
        'address_list',
    ]
    def __init__(self, gedcom_file: Path, only_use_photo_tags: bool = True) -> None:
        """Initialize the Gedcom handler and load people and places from the GEDCOM file."""
        self.gedcom_parser = GedcomParser(
            gedcom_file=gedcom_file,
            only_use_photo_tags=only_use_photo_tags
        )
        self.people = {}
        self.address_book = FuzzyAddressBook()

        self._parse_people()

    def close(self):
        """
        Close the GEDCOM parser and release any resources.
        """
        self.gedcom_parser.close()

    def _parse_people(self) -> Dict[str, Person]:
        """
        Parse people from the GEDCOM file and populate the people dictionary.

        Returns:
            Dict[str, Person]: Dictionary of Person objects indexed by xref_id.
        """
        self.people = self.gedcom_parser.parse_people()
        return self.people

    # def get_full_address_book(self) -> FuzzyAddressBook:
    #     """
    #     Get all places from the GEDCOM file as a FuzzyAddressBook.

    #     Returns:
    #         FuzzyAddressBook: Address book containing all unique places.
    #     """
    #     self.address_book = self.gedcom_parser.get_full_address_book()
    #     return self.address_book

    def read_full_address_list(self) -> None:
        """
        Get all places from the GEDCOM file.

        Returns:
            List[str]: List of unique place names.
        """
        self.address_list = self.gedcom_parser.get_full_address_list()

    def filter_generations(
        self,
        starting_person_id: str,
        num_ancestor_generations: int,
        num_descendant_generations: int,
        wider_descendants_end_generation: Optional[int],
        include_partners: bool = False,
        include_siblings: bool = False
    ) -> Tuple[Dict[str, Person], str]:
        """
        Filter people to include ancestors and descendants of a starting person.

        Traverses the family tree starting from a given person, going back a specified
        number of generations to collect ancestors, then forward a specified number of
        generations to collect descendants. Optionally includes partners and siblings.

        Args:
            starting_person_id (str): The xref_id of the starting person.
            num_ancestor_generations (int): Number of generations to include for ancestors (negative direction).
            num_descendant_generations (int): Number of generations to include for descendants (positive direction).
            wider_descendants_end_generation (Optional[int]): If set, collect descendants from all ancestors up to this generation.
            include_partners (bool): Whether to include partners of collected individuals.
            include_siblings (bool): Whether to include siblings of collected individuals.

        Returns:
            Tuple[Dict[str, Person], str]:
                - Dictionary of filtered Person objects including the starting
                  person, their ancestors, descendants, and optionally partners/siblings.
                - Informational message summarizing the filtering.

        Raises:
            ValueError: If starting_person_id is not found in the people dictionary.
        """
        if starting_person_id not in self.people:
            raise ValueError(f"Person with ID '{starting_person_id}' not found in GEDCOM data")

        tracker = GenerationTracker()

        def _add_partners(person_id: str, generation: int):
            """Add partners of a person."""
            try:
                person = self.people[person_id]
                for partner in person.partners:
                    partner_id = partner.xref_id if hasattr(partner, 'xref_id') else partner
                    if not tracker.exists(partner_id):
                        logger.info(f"Gen {generation}: Collecting partner: {partner_id}: {self.people[partner_id].name if partner_id in self.people else partner_id}")
                        tracker.add(partner_id, generation)
            except KeyError:
                logger.warning(f"Person ID '{person_id}' not found while adding partners")

        def _add_siblings(person_id: str, generation: int):
            """Add siblings of a person."""
            try:
                person = self.people[person_id]
                if person.father and person.mother:
                    father = person.father.xref_id if hasattr(person.father, 'xref_id') else person.father
                    mother = person.mother.xref_id if hasattr(person.mother, 'xref_id') else person.mother
                    siblings_list = set()
                    siblings_list.update(self.people[father].children if father in self.people else [])
                    siblings_list.update(self.people[mother].children if mother in self.people else [])
                    for sibling_id in siblings_list:
                        if sibling_id != person_id and not tracker.exists(sibling_id):
                            logger.info(f"Gen {generation}: Collecting sibling: {sibling_id}: {self.people[sibling_id].name if sibling_id in self.people else sibling_id}")
                            tracker.add(sibling_id, generation)
            except KeyError:
                logger.warning(f"Person ID '{person_id}' not found while adding siblings")

        def _collect_ancestors(person_id: str, generation: int):
            """Recursively collect ancestors. Negative generation = earlier (ancestors)."""
            if abs(generation) < num_ancestor_generations or num_ancestor_generations == -1:
                is_last_generation = False
            else:
                is_last_generation = True
            try:
                person = self.people[person_id]
                if not tracker.exists(person_id):
                    logger.info(f"Gen {generation}: Collecting ancestor: {person_id}: {person.name}")
                    tracker.add(person_id, generation)
                if include_partners:
                    _add_partners(person_id, generation)
                if include_siblings and not is_last_generation:
                    _add_siblings(person_id, generation)
            except KeyError:
                logger.warning(f"Person ID '{person_id}' not found while collecting ancestors")
                return
            if not is_last_generation:
                next_generation = generation - 1
                if person.father:
                    _collect_ancestors(person.father.xref_id if hasattr(person.father, 'xref_id') else person.father, next_generation)
                if person.mother:
                    _collect_ancestors(person.mother.xref_id if hasattr(person.mother, 'xref_id') else person.mother, next_generation)

        _collect_ancestors(person_id=starting_person_id, generation=0)

        def _collect_descendants(person_id: str, generation: int, end_generation: Optional[int]):
            """Recursively collect descendants. Positive generation = later (descendants)."""
            if end_generation is None:
                is_last_generation = False
            elif generation < end_generation:
                is_last_generation = False
            else:
                is_last_generation = True
            try:
                if not tracker.exists(person_id):
                    logger.info(f"Gen {generation}: Collecting descendant: {person_id}: {self.people[person_id].name if person_id in self.people else person_id}")
                    tracker.add(person_id, generation)
                if include_partners:
                    _add_partners(person_id, generation)
            except KeyError:
                logger.warning(f"Person ID '{person_id}' not found while collecting descendants")
                return
            if not is_last_generation:
                next_generation = generation + 1
                person = self.people[person_id]
                for child_id in person.children:
                    _collect_descendants(child_id, next_generation, end_generation=end_generation)

        # Collect descendants from each ancestor
        if wider_descendants_end_generation is not None:
            earliest_gen = tracker.earliest_generation
            for generation in range(0, earliest_gen-1, -1):
                person_ids = tracker.get_generation(generation)
                for person_id in person_ids:
                    _collect_descendants(person_id=person_id, generation=generation, end_generation=wider_descendants_end_generation)

        # Collect descendants from the starting person if not already done above
        if wider_descendants_end_generation is None or wider_descendants_end_generation >= 0:
            _collect_descendants(person_id=starting_person_id, generation=0, end_generation=num_descendant_generations)

        all_ids = tracker.all()
        filtered_people = {person_id: self.people[person_id] for person_id in all_ids}

        earliest_gen = tracker.earliest_generation
        latest_gen = tracker.latest_generation
        num_generations = latest_gen - earliest_gen + 1
        message = (f"Filtered {len(filtered_people)} people from {len(self.people)} total "
                   f"({earliest_gen} earliest to {latest_gen} latest; {num_generations} generations) "
                   f"from person {self.people[starting_person_id].name}")
        logger.info(message)
        return filtered_people, message

    def find_person_by_name(self, name: str, exact_match: bool = False) -> List[str]:
        """
        Find person ID(s) by name.

        Searches through all people to find matching names. Can do exact or partial
        (case-insensitive) matching.

        Args:
            name (str): The name to search for.
            exact_match (bool): If True, requires exact match (case-insensitive).
                If False, matches if name appears anywhere in the person's name.

        Returns:
            List[str]: List of xref_ids for matching people (empty if no matches found).
        """
        matches = []
        search_name = name.lower().strip()
        
        for person_id, person in self.people.items():
            if person.name:
                person_name = person.name.lower()
                if exact_match:
                    if person_name == search_name:
                        matches.append(person_id)
                else:
                    if search_name in person_name:
                        matches.append(person_id)
        
        if matches:
            logger.info(f"Found {len(matches)} person(s) matching '{name}': {matches}")
        else:
            logger.warning(f"No person found with name '{name}'")
        return matches
        
    def export_people_with_photos(
        self,
        people: Dict[str, Person],
        output_filename: str,
        output_folder: Union[str, Path],
        photo_subdir: Union[str, Path]
    ) -> None:
        """
        Export all people to a new GEDCOM file, copying any referenced photo images to a new directory.

        Args:
            people (Dict[str, Person]): Dictionary of Person objects to export.
            output_filename (str): Name of the GEDCOM file to write.
            output_folder (Union[str, Path]): Folder to write the GEDCOM file.
            photo_subdir (Union[str, Path]): Directory to copy photo images into.
        """
        output_folder = Path(output_folder)
        photo_subdir = Path(photo_subdir) if photo_subdir else None
        self.gedcom_parser.gedcom_writer(people, output_filename, output_folder, photo_subdir)