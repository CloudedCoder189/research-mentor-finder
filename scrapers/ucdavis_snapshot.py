from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NOT_AVAILABLE = "Not publicly available"
SNAPSHOT_DATE = "2026-07-25"


@dataclass(frozen=True, slots=True)
class UCDavisSnapshotEntry:
    name: str
    title: str
    email: str
    profile_url: str
    website_url: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE


def snapshot_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", normalized.casefold())


# Dated transcription of the active Faculty section of the official UC Davis
# Computer Science directory. It is used only when every live official route is
# blocked. The department reports 43 faculty members as of this snapshot date.
UC_DAVIS_FACULTY_SNAPSHOT: tuple[UCDavisSnapshotEntry, ...] = (
    UCDavisSnapshotEntry("Zhaojun Bai", "Distinguished Professor", "bai@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/zhaojun-bai"),
    UCDavisSnapshotEntry("Hao Chen", "Professor", "chen@ucdavis.edu", "https://cs.ucdavis.edu/directory/hao-chen"),
    UCDavisSnapshotEntry("Muhao Chen", "Associate Professor", "muhchen@ucdavis.edu", "https://cs.ucdavis.edu/directory/muhao-chen"),
    UCDavisSnapshotEntry("Raissa M. D'Souza", "Professor and Associate Dean for Research", "rmdsouza@ucdavis.edu", "https://cs.ucdavis.edu/directory/raissa-d-souza"),
    UCDavisSnapshotEntry("Ian Davidson", "Professor", "davidson@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/ian-davidson"),
    UCDavisSnapshotEntry("David Doty", "Associate Professor", "doty@ucdavis.edu", "https://cs.ucdavis.edu/directory/david-doty"),
    UCDavisSnapshotEntry("Kurt Eiselt", "Professor of Teaching & Vice-Chair", "eiselt@ucdavis.edu", "https://cs.ucdavis.edu/directory/kurt-eiselt"),
    UCDavisSnapshotEntry("Matthew Farrens", "Professor", "farrens@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/matthew-farrens"),
    UCDavisSnapshotEntry("Vladimir Filkov", "Professor", "filkov@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/vladimir-filkov"),
    UCDavisSnapshotEntry("Alexander Gamero-Garrido", "Assistant Professor", "agamerog@ucdavis.edu", "https://cs.ucdavis.edu/directory/alexander-gamero-garrido-0", research_interests="Computer networking, Internet measurement, online privacy, technology policy, and public policy"),
    UCDavisSnapshotEntry("Dipak Ghosal", "Professor, Bucher Family Chair", "ghosal@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/dipak-ghosal"),
    UCDavisSnapshotEntry("Lifu Huang", "Associate Professor", "lfuhuang@ucdavis.edu", "https://cs.ucdavis.edu/people/lifu-huang", research_interests="Natural language processing, multimodal learning, machine learning, large language models, and vision-language models"),
    UCDavisSnapshotEntry("Isaac Kim", "Associate Professor", "ikekim@ucdavis.edu", "https://cs.ucdavis.edu/directory/isaac-kim"),
    UCDavisSnapshotEntry("Sam King", "Professor", "kingst@ucdavis.edu", "https://cs.ucdavis.edu/directory/sam-king"),
    UCDavisSnapshotEntry("Patrice Koehl", "Professor", "pakoehl@ucdavis.edu", "https://cs.ucdavis.edu/directory/patrice-koehl"),
    UCDavisSnapshotEntry("Greg Kuperberg", "Distinguished Professor", "greg@math.ucdavis.edu", "https://cs.ucdavis.edu/directory/greg-kuperberg"),
    UCDavisSnapshotEntry("Jasper Lee", "Assistant Professor", "jasperlee@ucdavis.edu", "https://cs.ucdavis.edu/people/jasper-lee", research_interests="Learning theory, machine learning, discrete optimization, and theory of computing"),
    UCDavisSnapshotEntry("Dongyu Liu", "Assistant Professor", "dyuliu@ucdavis.edu", "https://cs.ucdavis.edu/directory/dongyu-liu"),
    UCDavisSnapshotEntry("Xin Liu", "Professor", "liu@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/xin-liu", "https://xinliu.engineering.ucdavis.edu/"),
    UCDavisSnapshotEntry("Jason Lowe-Power", "Associate Professor", "jlowepower@ucdavis.edu", "https://cs.ucdavis.edu/directory/jason-lowe-power"),
    UCDavisSnapshotEntry("Kwan-Liu Ma", "Distinguished Professor", "ma@cs.ucdavis.edu", "https://cs.ucdavis.edu/directory/kwan-liu-ma"),
    UCDavisSnapshotEntry("Joshua McCoy", "Associate Professor", "jamccoy@ucdavis.edu", "https://cs.ucdavis.edu/directory/joshua-mccoy"),
    UCDavisSnapshotEntry("Slobodan Mitrovic", "Associate Professor", "smitrovic@ucdavis.edu", "https://cs.ucdavis.edu/directory/slobodan-mitrovic"),
    UCDavisSnapshotEntry("Michael Neff", "Professor, Chair of Graduate Group", "mpneff@ucdavis.edu", "https://cs.ucdavis.edu/directory/michael-neff"),
    UCDavisSnapshotEntry("Christopher Nitta", "Associate Professor of Teaching", "cjnitta@ucdavis.edu", "https://cs.ucdavis.edu/directory/christopher-nitta"),
    UCDavisSnapshotEntry("Randall O’Reilly", "Professor", "oreilly@ucdavis.edu", "https://cs.ucdavis.edu/directory/randall-o%27reilly"),
    UCDavisSnapshotEntry("Tapti Palit", "Assistant Professor", "tpalit@ucdavis.edu", "https://cs.ucdavis.edu/people/tapti-palit", research_interests="Program analysis, software security, systems, memory-safe code translation, and performance optimization"),
    UCDavisSnapshotEntry("Julian Panetta", "Associate Professor", "jpanetta@ucdavis.edu", "https://cs.ucdavis.edu/directory/julian-panetta"),
    UCDavisSnapshotEntry("Hamed Pirsiavash", "Associate Professor", "hpirsiav@ucdavis.edu", "https://cs.ucdavis.edu/directory/hamed-pirsiavash"),
    UCDavisSnapshotEntry("Joël Porquet-Lupine", "Associate Professor of Teaching", "jporquet@ucdavis.edu", "https://cs.ucdavis.edu/directory/joel-porquet-lupine", "https://luplab.cs.ucdavis.edu/"),
    UCDavisSnapshotEntry("Setareh Rafatirad", "Associate Professor of Teaching", "srafatirad@ucdavis.edu", "https://cs.ucdavis.edu/directory/setareh-rafatirad"),
    UCDavisSnapshotEntry("Amanda Raybuck", "Assistant Professor", "araybuck@ucdavis.edu", "https://cs.ucdavis.edu/people/amanda-raybuck", "https://web.cs.ucdavis.edu/~araybuck/", "Operating systems, datacenter systems, memory management, CXL, and emerging memory technologies"),
    UCDavisSnapshotEntry("Cindy Rubio González", "Professor", "crubio@ucdavis.edu", "https://cs.ucdavis.edu/directory/cindy-rubio-gonzalez", "https://web.cs.ucdavis.edu/~rubio/"),
    UCDavisSnapshotEntry("Mohammad Sadoghi", "Professor, Chancellor’s Fellow", "msadoghi@ucdavis.edu", "https://cs.ucdavis.edu/directory/mohammad-sadoghi", "https://expolab.org/"),
    UCDavisSnapshotEntry("Zubair Shafiq", "Professor", "zshafiq@ucdavis.edu", "https://cs.ucdavis.edu/directory/zubair-shafiq"),
    UCDavisSnapshotEntry("Maike Sonnewald", "Assistant Professor", "sonnewald@ucdavis.edu", "https://cs.ucdavis.edu/directory/maike-sonnewald", "https://www.msonnewald.com/"),
    UCDavisSnapshotEntry("Caleb Stanford", "Assistant Professor", "cdstanford@ucdavis.edu", "https://cs.ucdavis.edu/directory/caleb-stanford"),
    UCDavisSnapshotEntry("Ilias Tagkopoulos", "Professor", "tagkopou@cs.ucdavis.edu", "https://aifs.ucdavis.edu/about/people/ilias-tagkopoulos", research_interests="Bioinformatics, machine learning, artificial intelligence, data science, computational biology, and predictive analytics"),
    UCDavisSnapshotEntry("Aditya Thakur", "Associate Professor", "avthakur@ucdavis.edu", "https://cs.ucdavis.edu/directory/aditya-thakur"),
    UCDavisSnapshotEntry("Hao-Chuan Wang", "Professor", "hciwang@ucdavis.edu", "https://cs.ucdavis.edu/directory/hao-chuan-wang"),
    UCDavisSnapshotEntry("Jiawei Zhang", "Associate Professor", "jiwzhang@ucdavis.edu", "https://cs.ucdavis.edu/directory/jiawei-zhang"),
    UCDavisSnapshotEntry("Zhe Zhao", "Assistant Professor", "zao@ucdavis.edu", "https://cs.ucdavis.edu/people/zhe-zhao", research_interests="Deep learning, efficient and robust machine learning, natural language understanding, computer vision, and recommender systems"),
    UCDavisSnapshotEntry("Yang Zhou", "Assistant Professor", "yayzhou@ucdavis.edu", "https://cs.ucdavis.edu/people/yang-zhou", "https://yangzhou1997.github.io/"),
)
