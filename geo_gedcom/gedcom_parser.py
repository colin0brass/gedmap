"""
gedcom_parser.py - GEDCOM parsing and export utilities.

Defines the GedcomParser class for parsing GEDCOM files, extracting people and places, copying photo files, and exporting filtered GEDCOM data.
Supports robust handling of INDI/FAM records, photo management, and geocoding integration.

Author: @colin0brass
Last updated: 2025-11-29
"""
import os
import re
from typing import Dict, List, Optional, Union, Tuple
import tempfile
import shutil

import logging
from pathlib import Path

from ged4py.parser import GedcomReader
from ged4py.model import Record, NameRec
from .person import Person, LifeEvent
from .addressbook import FuzzyAddressBook

logger = logging.getLogger(__name__)

class GedcomParser:
    """
    Parses GEDCOM files and extracts people and places.

    Attributes:
        gedcom_file (Optional[Path]): Path to GEDCOM file.
        _cached_people (Optional[Dict[str, Person]]): Cached people dictionary.
        _cached_address_book (Optional[FuzzyAddressBook]): Cached address book.
        only_use_photo_tags (bool): Whether to use only _PHOTO tags for photos.
        simplify_date (bool): Whether to simplify date parsing.
        simplify_range_policy (str): Policy for range simplification ('first', 'approximate').
    """
    __slots__ = [
        'gedcom_file',
        '_cached_people', '_cached_address_book',
        'only_use_photo_tags',
        'simplify_date',
        'simplify_range_policy'
    ]

    LINE_RE = re.compile(
        r'^(\d+)\s+(?:@[^@]+@\s+)?([A-Z0-9_]+)(.*)$'
    )  # allow optional @xref@ before the tag

    def __init__(self, gedcom_file: Path = None, only_use_photo_tags: bool = True) -> None:
        """
        Initialize GedcomParser.

        Args:
            gedcom_file (Path): Path to GEDCOM file.
        """
        self.gedcom_file = self.check_fix_gedcom(gedcom_file)
        # caches populated by _load_people_and_places()
        self._cached_people = None
        self._cached_address_book = None
        self.only_use_photo_tags = only_use_photo_tags
        self.simplify_date = True
        self.simplify_range_policy = 'first'  # 'first' or 'approximate'

    def close(self):
        """Placeholder for compatibility."""
        pass

    def check_fix_gedcom(self, input_path: Path) -> Path:
        """Fixes common issues in GEDCOM records."""
        if input_path is None:
            return None
        temp_fd, temp_path = tempfile.mkstemp(suffix='.ged')
        os.close(temp_fd)
        changed = self.fix_gedcom_conc_cont_levels(input_path, temp_path)
        if changed:
            logger.warning(f"Checked and made corrections to GEDCOM file '{input_path}' saved as {temp_path}")
        return temp_path if changed else input_path

    def fix_gedcom_conc_cont_levels(self, input_path: Path, temp_path: Path) -> bool:
        """
        Fixes GEDCOM continuity and structure levels.
        These types of GEDCOM issues have been seen from Family Tree Maker exports.
        If not fixed, they can cause failure to parse the GEDCOM file correctly.
        """

        cont_level = None
        changed = False

        try:
            with open(input_path, 'r', encoding='utf-8', newline='', errors="replace") as infile, \
                open(temp_path, 'w', encoding='utf-8', newline='') as outfile:
                for raw in infile:
                    line = raw.rstrip('\r\n')
                    m = self.LINE_RE.match(line)
                    if not m:
                        outfile.write(raw)
                        continue

                    level_s, tag, rest = m.groups()
                    level = int(level_s)

                    if tag in ('CONC', 'CONT'):
                        fixed_level = cont_level if cont_level is not None else level
                        outfile.write(f"{fixed_level} {tag}{rest}\n")
                        if fixed_level != level:
                            changed = True
                    else:
                        cont_level = level + 1
                        outfile.write(raw)
        except IOError as e:
            logger.error(f"Failed to fix GEDCOM file {input_path}: {e}")
        return changed

    def __get_event_location(self, record: Record) -> Optional[LifeEvent]:
        """
        Creates a LifeEvent from a record.

        Args:
            record (Record): GEDCOM record.

        Returns:
            Optional[LifeEvent]: LifeEvent object or None.
        """
        event = None
        if record:
            place = record.sub_tag('PLAC').value if record.sub_tag('PLAC') else None
            date = record.sub_tag('DATE').value if record.sub_tag('DATE') else None
            event = LifeEvent(
                place = place,
                date = date,
                record=record,
                what=record.tag)
        return event

    def __create_person(self, record: Record) -> Person:
        """
        Creates a Person object from a record.

        Args:
            record (Record): GEDCOM record.

        Returns:
            Person: Person object.
        """


        person = Person(record.xref_id)
        person.name = ''
        name: NameRec = record.sub_tag('NAME')
        if name:
            person.firstname = record.name.first
            person.surname = record.name.surname
            person.maidenname = record.name.maiden
            person.name = f'{record.name.format()}'
        if person.name == '':
            person.firstname = 'Unknown'
            person.surname = 'Unknown'
            person.maidenname = 'Unknown'
            person.name = 'Unknown'
        person.sex = record.sex
        person.birth = self.__get_event_location(record.sub_tag('BIRT'))
        person.death = self.__get_event_location(record.sub_tag('DEAT'))
        title = record.sub_tag("TITL")
        person.title = title.value if title else ""

        # Extract residences
        person.residences = self._get_residences(record)

        # Grab photos
        photos_all, preferred_photos = self._extract_photos_from_record(record)
        person.photos_all = photos_all
        if preferred_photos:
            person.photo = preferred_photos[0]
        elif photos_all:
            person.photo = photos_all[0]
        else:
            person.photo = None

        return person

    def _get_residences(self, record: Record) -> List[LifeEvent]:
        """
        Extracts residence places from a Record.

        Args:
            record (Record): GEDCOM record.

        Returns:
            List[str]: List of residence places.
        """
        residences = []
        for event_tag in ['RESI', 'ADDR']:
            for event_record in record.sub_tags(event_tag):
                event = self.__get_event_location(event_record)
                if event.place:
                    residences.append(event)

        return residences
    
    def _extract_photos_from_record(self, record: Record) -> Tuple[List[str], List[str]]:
        """
        Extracts all valid photo file paths from a GEDCOM record.

        Args:
            record (Record): GEDCOM record.
        """
        photos = []
        preferred_photos = []
        # MyHeritage and possibly others use _PHOTO tag for preferred photos
        for obj in record.sub_tags("_PHOTO"):
            files, _ = self._extract_photo(obj)
            preferred_photos.extend(files)
        if not self.only_use_photo_tags:
            # Standard OBJE tags, possibly with "_PRIM" sub-tag for preferred photos
            for obj in record.sub_tags("OBJE"):
                files, preferred_files = self._extract_photo(obj)
                photos.extend(files)
                preferred_photos.extend(preferred_files)
        return photos, preferred_photos
    
    def _extract_photo(self, obj: Record) -> Tuple[List[str], List[str]]:
        """
        Extracts all valid photo file paths from a GEDCOM record's OBJE tags.

        Args:
            record (Record): GEDCOM record.

        Returns:
            list: List of valid photo file paths (strings).
        """
        allowed_exts = {'jpg', 'jpeg', 'bmp', 'png', 'gif'}
        photos = []
        preferred_photos = []
        file_tag = obj.sub_tag("FILE")
        if file_tag:
            file_value = file_tag.value
            ext = file_value.lower().split('.')[-1]
            form_tags = [t for t in obj.sub_tags("FORM") if t.value]
            form_exts = [form_tag.value.lower() for form_tag in form_tags]
            if ext in allowed_exts or any(f in allowed_exts for f in form_exts):
                photos.append(file_value)
                prim_tag = obj.sub_tag("_PRIM")
                if prim_tag and prim_tag.value.upper() != 'N':
                    preferred_photos.append(file_value)

        return photos, preferred_photos
    
    def __create_people(self, records0) -> Dict[str, Person]:
        """
        Creates a dictionary of Person objects from records.

        Args:
            records0: GEDCOM records.

        Returns:
            Dict[str, Person]: Dictionary of Person objects.
        """
        people = {}
        for record in records0('INDI'):
            people[record.xref_id] = self.__create_person(record)
        return people

    def __add_marriages(self, people: Dict[str, Person], records) -> Dict[str, Person]:
        """
        Adds marriages and parent/child relationships to people.

        Args:
            people (Dict[str, Person]): Dictionary of Person objects.
            records: GEDCOM records.

        Returns:
            Dict[str, Person]: Updated dictionary of Person objects.
        """
        for record in records('FAM'):
            # Get partner list from family record
            # Including non-traditional families by collecting all partners
            partner_person_list = []
            for partner_tag in ['HUSB', 'WIFE']:
                partner_record = record.sub_tag(partner_tag)
                if partner_record and partner_record.xref_id not in people:
                    # Create minimal Person if not already present
                    people[partner_record.xref_id] = self.__create_person(partner_record)
                partner_person = people.get(partner_record.xref_id) if partner_record else None
                if partner_person:
                    partner_person_list.append(partner_person)

            if len(partner_person_list) > 2:
                logger.warning(f"Family record {record.xref_id} has unexpected number of partners: {len(partner_person_list)}.")

            # Link partners to each other
            partner_set = set(partner_person_list)
            for person in partner_person_list:
                other_people = partner_set - {person}
                if other_people:
                    for other_person in other_people:
                        if other_person and other_person.xref_id not in person.partners:
                            person.partners.append(other_person.xref_id)

            # Add marriage events
            for marriages in record.sub_tags('MARR'):
                marriage_event = self.__get_event_location(marriages)
                for person in partner_person_list:
                    person.marriages.append(marriage_event)

            for child in record.sub_tags('CHIL'):
                if child.xref_id in people:
                    if people[child.xref_id]:
                        for partner_person in partner_person_list:
                            if record.sub_tag('HUSB') and partner_person.xref_id == record.sub_tag('HUSB').xref_id:
                                people[child.xref_id].father = partner_person.xref_id
                                partner_person.children.append(child.xref_id)
                            if record.sub_tag('WIFE') and partner_person.xref_id == record.sub_tag('WIFE').xref_id:
                                people[child.xref_id].mother = partner_person.xref_id
                                partner_person.children.append(child.xref_id)

        return people

    def parse_people(self) -> Dict[str, Person]:
        """
        Parses people from the GEDCOM file.

        Returns:
            Dict[str, Person]: Dictionary of Person objects.
        """
        if self._cached_people:
            return self._cached_people
        self._load_people_and_places()
        return self._cached_people if self._cached_people else {}

    def _fast_count(self) -> None:
        def _count_gedcom_records( path, encoding):
                """Return (people, families) counts for a GEDCOM file with given encoding."""
                people = families = 0
                with open(path, encoding=encoding) as f:
                    for line in f:
                        if line.startswith("0 @") and " INDI" in line:
                            people += 1
                        elif line.startswith("0 @") and " FAM" in line:
                            families += 1
                return people, families

        encodings = ["utf-8", "latin-1"]  # try in order
        for enc in encodings:
            try:
                people, families = _count_gedcom_records(str(self.gedcom_file), enc)
                logger.info(f"Fast count people {people} & families {families}")
                return
            except UnicodeDecodeError:
                # try next encoding
                continue
            except Exception as e:
                logger.error(
                    f"Error fast counting people and families from GEDCOM file '{self.gedcom_file}' with encoding {enc}: {e}"
                )
                return
        # If we get here, all encodings failed
        logger.error(f"Could not decode GEDCOM file '{self.gedcom_file}' with any known encoding")

    def _load_people_and_places(self):
        """
        Loads people and places from the GEDCOM file.
        """

        try:
            # Single pass: build people and then addresses
            with GedcomReader(str(self.gedcom_file)) as g:
                records = g.records0
                self._cached_people = self.__create_people(records)
                self._cached_people = self.__add_marriages(self._cached_people, records)

                # Now extract places
                # (considered to extract from people, however suspect that might risk missing some record types)
                self._cached_address_book = FuzzyAddressBook()
                for indi in records('INDI'):
                    for ev in indi.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            self._cached_address_book.fuzzy_add_address(place, None)

                for fam in records('FAM'):
                    for ev in fam.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            self._cached_address_book.fuzzy_add_address(place, None)

        except Exception as e:
            logger.error(f"Error extracting people & places from GEDCOM file '{self.gedcom_file}': {e}")

    # def get_full_address_book(self) -> FuzzyAddressBook:
    #     """
    #     Returns address book of all places found in the GEDCOM file.

    #     Returns:
    #         FuzzyAddressBook: Address book of places.
    #     """

    #     # Return cached if available
    #     if self._cached_address_book:
    #         return self._cached_address_book
    #     self._load_people_and_places()
    #     return self._cached_address_book if self._cached_address_book else FuzzyAddressBook()

    def get_full_address_list(self) -> List[str]:
        """
        Returns a list of all unique places found in the GEDCOM file.

        Returns:
            List[str]: List of unique place names.
        """
        address_list = []
        try:
            with GedcomReader(str(self.gedcom_file)) as g:
                # Individuals: collect PLAC under any event (BIRT/DEAT/BAPM/MARR/etc.)
                for indi in g.records0("INDI"):
                    for ev in indi.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            address_list.append(place)

            with GedcomReader(str(self.gedcom_file)) as g:
                # Individuals: collect PLAC under any event (BIRT/DEAT/BAPM/MARR/etc.)
                for indi in g.records0("INDI"):
                    for ev in indi.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            address_list.append(place)

                # Families: marriage/divorce places, etc.
                for fam in g.records0("FAM"):
                    for ev in fam.sub_records:
                        plac = ev.sub_tag_value("PLAC")
                        if plac:
                            place = plac.strip()
                            address_list.append(place)
        except Exception as e:
            logger.error(f"Error extracting places from GEDCOM file '{self.gedcom_file}': {e}")
        return address_list
    
    def gedcom_writer(self, people: Dict[str, Person], output_filename: str, output_folder: Path, photo_subdir: Union[Path, None]):
        """
        Write a GEDCOM file from a dictionary of Person objects.

        Args:
            people (Dict[str, Person]): Dictionary of Person objects to write.
            output_filename (str): Name of the GEDCOM file to write.
            output_folder (Path): Folder to write the GEDCOM file.
            photo_subdir (Optional[Path]): If provided, copy photo files to this directory and update references.
        """
        output_path = output_folder / output_filename
        photo_dir = None
        if photo_subdir:
            photo_dir = output_path.parent / photo_subdir
            photo_dir.mkdir(parents=True, exist_ok=True)

        fam_map = self._build_family_map(people)
        fam_id_map = self._assign_family_ids(fam_map)
        self._assign_family_links(people, fam_map, fam_id_map)
        self._write_gedcom_file(people, fam_map, fam_id_map, output_path, photo_dir)

    def _build_family_map(self, people: Dict[str, Person]) -> dict:
        """
        Build a mapping of families (partners and children) from people.
        Returns: fam_map: dict mapping (father, mother) or (partner1, partner2) to set of children.
        """
        fam_map = {}
        # 1. Add families with children (parent-child families)
        for person in people.values():
            father = getattr(person, 'father', None)
            mother = getattr(person, 'mother', None)
            if father not in people:
                father = None
            if mother not in people:
                mother = None
            if father or mother:
                fam_key = (str(father) if father else '', str(mother) if mother else '')
                if fam_key not in fam_map:
                    fam_map[fam_key] = set()
                fam_map[fam_key].add(person.xref_id)
        # 2. Add partner-only families (no children)
        partner_fam_keys = set()
        for person in people.values():
            partners = getattr(person, 'partners', [])
            for partner_id in partners:
                if partner_id in people:
                    key = tuple(sorted([person.xref_id, partner_id]))
                    fam_key1 = (person.xref_id, partner_id)
                    fam_key2 = (partner_id, person.xref_id)
                    if fam_key1 in fam_map or fam_key2 in fam_map:
                        continue
                    if key not in partner_fam_keys:
                        partner_fam_keys.add(key)
                        fam_map[key] = set()  # No children
        return fam_map

    def _assign_family_ids(self, fam_map: dict) -> dict:
        """
        Assign unique family IDs to each family in fam_map.
        Returns: fam_id_map: dict mapping fam_key to family ID string.
        """
        fam_id_map = {}
        fam_count = 1
        for fam_key in fam_map:
            fam_id = f"@F{fam_count:04d}@"
            fam_id_map[fam_key] = fam_id
            fam_count += 1
        return fam_id_map

    def _assign_family_links(self, people: Dict[str, Person], fam_map: dict, fam_id_map: dict) -> None:
        """
        Assign FAMS (as spouse) and FAMC (as child) to each person based on family mappings.
        """
        for fam_key, fam_id in fam_id_map.items():
            if len(fam_key) == 2:
                a, b = fam_key
                children = fam_map[fam_key]
                if a and a in people:
                    if not hasattr(people[a], 'family_spouse'):
                        people[a].family_spouse = []
                    people[a].family_spouse.append(fam_id)
                if b and b in people:
                    if not hasattr(people[b], 'family_spouse'):
                        people[b].family_spouse = []
                    people[b].family_spouse.append(fam_id)
                for child in children:
                    if child in people:
                        if not hasattr(people[child], 'family_child'):
                            people[child].family_child = []
                        people[child].family_child.append(fam_id)

    def _write_gedcom_file(self, people: Dict[str, Person], fam_map: dict, fam_id_map: dict, output_path: Path, photo_dir: Optional[Path]) -> None:
        """
        Write the GEDCOM file to disk, including INDI and FAM records.
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("0 HEAD\n")
            f.write("1 SOUR gedcom_filter\n")
            f.write("1 GEDC\n2 VERS 5.5.1\n")
            f.write("1 CHAR UTF-8\n")
            for person in people.values():
                self._write_person_gedcom(f, person, output_path, photo_dir)
            for fam_key, children in fam_map.items():
                fam_id = fam_id_map[fam_key]
                self._write_family_gedcom(f, fam_id, fam_key, children)

    def _write_person_gedcom(self, f, person: Person, output_path: Path, photo_subdir: Optional[Path]) -> None:
        """
        Write an individual (INDI) record to the GEDCOM file.
        Args:
            f: File object to write to.
            person (Person): The person to write.
            output_path (Path): Path to the GEDCOM file.
            photo_subdir (Optional[Path]): Directory for photos, if any.
        """
        import shutil
        f.write(f"0 {person.xref_id} INDI\n")
        if person.name:
            f.write(f"1 NAME {person.name}\n")
        if person.sex:
            f.write(f"1 SEX {person.sex}\n")
        if person.birth:
            f.write("1 BIRT\n")
            if person.birth.date:
                date_str = person.birth.date.resolved
                if date_str:
                    f.write(f"2 DATE {date_str}\n")
            if person.birth.place:
                f.write(f"2 PLAC {person.birth.place}\n")
        if person.death:
            f.write("1 DEAT\n")
            if person.death.date:
                date_str = person.death.date.resolved
                if date_str:
                    f.write(f"2 DATE {date_str}\n")
            if person.death.place:
                f.write(f"2 PLAC {person.death.place}\n")
        # Write FAMS (spouse family) and FAMC (child family)
        for fams in getattr(person, 'family_spouse', []):
            f.write(f"1 FAMS {fams}\n")
        for famc in getattr(person, 'family_child', []):
            f.write(f"1 FAMC {famc}\n")
        # Write photo if present
        if person.photo and output_path is not None:
            src_photo = Path(person.photo)
            # Clean filename: replace spaces and special characters (except . and extension) with underscores
            # Keep bracket contents
            name_part, ext = os.path.splitext(src_photo.name)
            # Replace any sequence of non-alphanumeric (except .) with _
            cleaned_name = re.sub(r'[^A-Za-z0-9]+', '_', name_part) + ext
            if photo_subdir:
                dest_photo = photo_subdir / cleaned_name
                file_path = f"{photo_subdir.name}/{cleaned_name}"
            else:
                dest_photo = output_path.parent / cleaned_name
                file_path = cleaned_name
            try:
                shutil.copy2(src_photo, dest_photo)
            except Exception as e:
                logger.warning(f"Could not copy photo {src_photo} to {dest_photo}: {e}")
            f.write("1 OBJE\n")
            f.write(f"2 FILE {file_path}\n")
            ext = dest_photo.suffix[1:].lower()
            if ext:
                f.write(f"2 FORM {ext}\n")

    def _write_family_gedcom(self, f, fam_id: str, fam_key: tuple, children: set) -> None:
        """
        Write a family (FAM) record to the GEDCOM file.
        Args:
            f: File object to write to.
            fam_id (str): Family ID.
            fam_key (tuple): Family key (father, mother) or (partner1, partner2).
            children (set): Set of children xref IDs.
        """
        father, mother = fam_key
        f.write(f"0 {fam_id} FAM\n")
        if father:
            f.write(f"1 HUSB {father}\n")
        if mother:
            f.write(f"1 WIFE {mother}\n")
        for child in children:
            f.write(f"1 CHIL {child}\n")