"""Explicit topic aliases and token-safe matching; no provider calls."""
import re


def normalize(text: str) -> str:
    text = str(text).lower().replace("&", " and ").replace("-", " ")
    return " ".join(re.sub(r"[^a-z0-9+ ]", " ", text).split())


TOPIC_VARIANTS = {
    "climate and the environment": ("climate", "environmental science", "sustainability"),
    "astronomy and astrophysics": ("astronomy", "astrophysics"),
    "computer systems": ("computer systems", "operating systems", "distributed systems", "computer architecture"),
    "materials science": ("materials science", "materials engineering"),
    "renewable energy": ("renewable energy", "solar energy", "wind energy"),
    "computational neuroscience": ("computational neuroscience", "neural computation"),
    "human computer interaction": ("human computer interaction", "hci"),
    "machine learning": ("machine learning", "ml"),
    "artificial intelligence": ("artificial intelligence", "ai"),
    "ai": ("artificial intelligence", "ai"),
    "ml": ("machine learning", "ml"),
    "nlp": ("natural language processing", "nlp"),
    "robotics": ("robotics", "robot learning", "robot control"),
}


def term_variants(term: str) -> tuple[str, ...]:
    normalized = normalize(term)
    if not normalized:
        return ()
    variants = [normalized, *TOPIC_VARIANTS.get(normalized, ())]
    # Preserve ordinary plural noun matches without accepting arbitrary substrings.
    last_word = normalized.split()[-1]
    if len(last_word) >= 4 and last_word.isalpha() and not last_word.endswith("s"):
        variants.append(normalized + "s")
    return tuple(dict.fromkeys(variants))


def contains_term(corpus: str, term: str) -> bool:
    # '+' belongs to programming-language names: C must not match C++.
    return bool(term) and bool(re.search(rf"(?<![a-z0-9+]){re.escape(term)}(?![a-z0-9+])", corpus))
