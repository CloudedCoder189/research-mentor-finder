from __future__ import annotations

from scrapers.base import BaseUniversityScraper
from scrapers.broadened import (
    BroadenedBerkeleyScraper,
    BroadenedUCSBScraper,
    BroadenedUCSDScraper,
    BroadenedUCSCScraper,
)
from scrapers.calpoly import CalPolySLOScraper
from scrapers.caltech import CaltechScraper
from scrapers.osu import OregonStateUniversityScraper
from scrapers.psu import PortlandStateUniversityScraper
from scrapers.scu import SCUScraper
from scrapers.sdsu import SDSUScraper
from scrapers.sjsu import SJSUScraper
from scrapers.stanford import StanfordScraper
from scrapers.ucdavis import UCDavisScraper
from scrapers.uci import UCIScraper
from scrapers.ucla import UCLAScraper
from scrapers.uo import UniversityOfOregonScraper
from scrapers.usc import USCScraper
from scrapers.uw import UniversityOfWashingtonScraper
from scrapers.wsu import WashingtonStateUniversityScraper
from scrapers.wwu import WesternWashingtonUniversityScraper

SCRAPERS: list[type[BaseUniversityScraper]] = [
    StanfordScraper,
    BroadenedBerkeleyScraper,
    UCLAScraper,
    BroadenedUCSDScraper,
    SJSUScraper,
    USCScraper,
    UCDavisScraper,
    UCIScraper,
    BroadenedUCSBScraper,
    BroadenedUCSCScraper,
    CaltechScraper,
    SCUScraper,
    CalPolySLOScraper,
    SDSUScraper,
    OregonStateUniversityScraper,
    UniversityOfOregonScraper,
    PortlandStateUniversityScraper,
    UniversityOfWashingtonScraper,
    WashingtonStateUniversityScraper,
    WesternWashingtonUniversityScraper,
]

IMPLEMENTED_SCRAPERS: dict[str, type[BaseUniversityScraper]] = {
    scraper.university_name: scraper for scraper in SCRAPERS
}
