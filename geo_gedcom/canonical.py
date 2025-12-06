import re
import logging
from typing import Dict, List, Tuple
from unidecode import unidecode
from deepparse.parser import AddressParser

from .geo_config import GeoConfig

# Re-use higher-level logger (inherits configuration from main script)
logger = logging.getLogger(__name__)

class Canonical:
    """
    Provides canonicalization utilities for addresses, including normalization,
    expansion of variants, parsing, and construction of canonical address strings.

    Attributes:
        geo_config (GeoConfig): Geographic configuration instance.
        parser (AddressParser): Deepparse address parser instance.
    """

    SPACE_RE = re.compile(r"\s+")
    PUNC_RE = re.compile(r"[\,;]+")

    DEEPPARSE_DEVICE = "cpu"  # or "cuda" if GPU available
    DEEPPARSE_OFFLINE = True  # Deepparse offline mode

    def __init__(self, geo_config: GeoConfig = None):
        """
        Initialize Canonical with country data from pycountry and optional config file.

        Args:
            geo_config (GeoConfig, optional): GeoConfig instance with geographic data.
        """
        self.geo_config = geo_config if geo_config else GeoConfig()
        logger.info(f"Using Deepparse device: {self.DEEPPARSE_DEVICE}, offline: {self.DEEPPARSE_OFFLINE}")
        self.parser = AddressParser(model_type="bpemb",
                                    device=self.DEEPPARSE_DEVICE,
                                    offline=self.DEEPPARSE_OFFLINE)

    def __strip_and_norm(self, address: str) -> str:
        """
        Normalize and strip an address string.

        Args:
            address (str): Address string.

        Returns:
            str: Normalized address.
        """
        if not address: return ""
        address = unidecode(address)
        address = address.strip()
        address = self.PUNC_RE.sub(",", address)
        address = self.SPACE_RE.sub(" ", address)
        return address

    def __expand_variants(self, address: str, max_variants=8) -> List[str]:
        """
        Deepparse does not provide expansion variants like libpostal.
        This returns the normalized address as a single variant.

        Args:
            address (str): Address string.
            max_variants (int): Ignored.

        Returns:
            List[str]: List with one normalized address.
        """
        return [self.__strip_and_norm(address)]

    def __parse_address(self, address: str) -> Dict[str, str]:
        """
        Parse an address string into its components using Deepparse.

        Args:
            address (str): Address string.

        Returns:
            Dict[str, str]: Dictionary of parsed address parts.
        """
        parsed = self.parser(address)
        # Deepparse returns a list of Address objects; take the first
        if parsed:
            parts = parsed[0].to_dict()
            # Normalize all values
            return {k: self.__strip_and_norm(str(v)) for k, v in parts.items()}
        return {}

    def __canonical_city(self, city: str) -> str:
        """
        Returns the normalized city name.

        Args:
            city (str): City name.

        Returns:
            str: Canonical city name.
        """
        return self.__strip_and_norm(city)

    def __canonical_country(self, country: str) -> str:
        """
        Returns the normalized country name.

        Args:
            country (str): Country name.

        Returns:
            str: Canonical country name.
        """
        return self.__strip_and_norm(country)

    def __canonicalise_parts(self, parts: Dict[str, str]) -> Tuple[Dict[str, str], str]:
        """
        Canonicalize address parts and construct a canonical address string.

        Args:
            parts (Dict[str, str]): Dictionary of address parts.

        Returns:
            Tuple[Dict[str, str], str]: (Canonicalized parts, canonical address string)
        """
        ordered_keys = ['house_number', 'road', 'suburb', 'city', 'state', 'postcode', 'country']
        canonical_parts = {key: parts.get(key, '') for key in ordered_keys if parts.get(key)}
        canonical_parts['city'] = self.__canonical_city(canonical_parts.get('city', ''))
        canonical_parts['country'] = self.__canonical_country(canonical_parts.get('country', ''))
        segments = list(canonical_parts.values())
        segments = [s for i, s in enumerate(segments) if s and s not in segments[:i]]
        canonical_address = ', '.join(segments)
        return canonical_parts, canonical_address

    def get_canonical(self, address: str, country_name: str = None) -> Tuple[str, Dict[str, str]]:
        """
        Get the canonical address string and parts for a given address.

        Args:
            address (str): Address string.
            country_name (str, optional): Country name to use if missing.

        Returns:
            Tuple[str, Dict[str, str]]: (Canonical address string, canonical parts dictionary)
        """
        address_clean = self.__strip_and_norm(address)
        address_variants = self.__expand_variants(address_clean)
        best_variant_canonical = None
        best_len = -1
        for variant in address_variants:
            address_parts = self.__parse_address(variant)
            address_parts, address_canonical = self.__canonicalise_parts(address_parts)
            if 'city' in address_parts and 'country' in address_parts:
                if len(address_canonical) > best_len:
                    best_variant_canonical = address_canonical
                    best_len = len(address_canonical)

        if not country_name or country_name.lower() in ('', 'none'):
            if self.geo_config.default_country and self.geo_config.default_country.lower() != 'none':
                country_name = self.geo_config.default_country

        if address_parts.get('country', '') == '' and country_name is not None:
            address_parts['country'] = country_name
            if best_variant_canonical:
                best_variant_canonical = f"{best_variant_canonical}, {address_parts['country']}"
            else:
                best_variant_canonical = address_parts['country']
        return best_variant_canonical, address_parts
