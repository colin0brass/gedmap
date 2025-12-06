# geo_gedcom Python Module

This module provides core functionality for parsing, filtering, and exporting GEDCOM genealogical data. It is designed for modularity, maintainability, and robust handling of genealogical records, including people, places, events, and photos.

## Requirements
- [ged4py](https://pypi.org/project/ged4py/)
- [rapidfuzz](https://pypi.org/project/rapidfuzz/)

## Key Features
- **GEDCOM Parsing:** Efficiently parses GEDCOM files and extracts individuals, families, events, and places.
- **Filtering:** Supports advanced ancestor/descendant filtering by generation.
- **Photo Management:** Handles photo file extraction and management from GEDCOM records.
- **Geocoding Integration:** Integrates with geolocation utilities for mapping places and events.
- **Export Utilities:** Allows exporting filtered data and associated photos to new GEDCOM files.
- **Memory Optimization:** Uses `__slots__` in key classes for reduced memory usage.
- **Type Hints & Docstrings:** All major classes and functions are documented and typed for clarity and maintainability.

## Main Classes & Modules
- `Gedcom`: High-level handler for people and places.
- `GedcomParser`: Utilities for parsing and exporting GEDCOM data.
- `Person`, `LifeEvent`: Data models for individuals and their life events.
- `Location`, `LatLon`: Geocoding and location utilities.
- `FuzzyAddressBook`: Place/address management.
- `GedcomDate`: Robust date parsing and normalization.

## Usage Example
```python
from geo_gedcom import Gedcom

gedcom_file = "Tree_2025-12-04.ged"
g = Gedcom(gedcom_file, only_use_photo_tags=True)
filtered, msg = g.filter_generations(
    starting_person_id="@I1@",
    num_ancestor_generations=3,
    num_descendant_generations=2,
    wider_descendants_end_generation=None,
    include_partners=True,
    include_siblings=True
)
print(msg)
g.export_people_with_photos(filtered, "filtered.ged", "output", "photos")
```

## Directory Structure
```
geo_gedcom/
├── __init__.py
├── gedcom.py
├── gedcom_parser.py
├── person.py
├── location.py
├── lat_lon.py
├── addressbook.py
├── gedcom_date.py
└── README.md
```

## Authors
- @colin0brass
- @lmallez
- @D-jeffrey

## License
See the main repository LICENSE.txt for details.

## Extending & Contributing
Contributions and extensions are welcome! Please see the main repository for guidelines and open an issue or pull request for major changes.
