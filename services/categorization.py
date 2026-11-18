from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable

# Ordered from specific to broad so a profile can receive useful subfield labels.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Large Language Models": (
        "large language model", "large language models", "llm", "foundation model",
        "foundation models", "language model", "language models",
    ),
    "Generative AI": (
        "generative ai", "generative artificial intelligence", "diffusion model",
        "diffusion models", "text generation", "image generation",
    ),
    "Reinforcement Learning": (
        "reinforcement learning", "interactive learning", "policy learning",
        "reward learning", "imitation learning",
    ),
    "Deep Learning": (
        "deep learning", "neural network", "neural networks", "representation learning",
    ),
    "Machine Learning": (
        "machine learning", "statistical learning", "learning algorithms",
        "learning theory", "predictive modeling", "predictive modelling",
    ),
    "Natural Language Processing": (
        "natural language processing", "computational linguistics", "language processing",
        "text mining", "natural language", "nlp",
    ),
    "Speech": (
        "speech recognition", "speech processing", "spoken language", "audio processing",
    ),
    "Information Retrieval": (
        "information retrieval", "search engines", "web search", "recommendation systems",
        "recommender systems",
    ),
    "Computer Vision": (
        "computer vision", "visual recognition", "image recognition", "image understanding",
        "visual computing", "medical imaging", "scene understanding",
    ),
    "Robotics": (
        "robotics", "robot learning", "robotic", "manipulation", "motion planning",
        "human-robot interaction",
    ),
    "Autonomous Systems": (
        "autonomous systems", "autonomous vehicles", "self-driving", "control systems",
        "intelligent systems",
    ),
    "AI Safety": (
        "ai safety", "artificial intelligence safety", "alignment", "responsible ai",
        "trustworthy ai", "human-compatible ai", "adversarial machine learning",
    ),
    "Human-Centered AI": (
        "human-centered ai", "human centred ai", "human-ai interaction",
        "human ai interaction", "human-compatible artificial intelligence",
    ),
    "Artificial Intelligence": (
        "artificial intelligence", "ai research", "machine intelligence",
        "intelligent agents", "automated reasoning",
    ),
    "Human-Computer Interaction": (
        "human-computer interaction", "human computer interaction", "hci",
        "user experience", "interactive systems", "ubiquitous computing",
    ),
    "Probabilistic Modeling": (
        "probabilistic modeling", "probabilistic modelling", "probabilistic reasoning",
        "bayesian", "causal inference", "uncertainty",
    ),
    "Data Science": (
        "data science", "data mining", "data analytics", "big data", "data analysis",
    ),
    "Optimization": (
        "optimization", "optimisation", "operations research", "convex optimization",
    ),
    "Theory": (
        "theoretical computer science", "algorithms", "complexity theory", "cryptography",
        "combinatorics", "theory of computation",
    ),
    "Systems": (
        "computer systems", "distributed systems", "operating systems", "networking",
        "databases", "computer architecture", "programming systems", "cloud computing",
    ),
    "Security & Privacy": (
        "cybersecurity", "computer security", "security", "privacy", "secure systems",
    ),
    "Graphics": (
        "computer graphics", "graphics", "animation", "rendering", "visualization",
    ),
    "Computational Biology": (
        "computational biology", "bioinformatics", "genomics", "biomedical data science",
    ),
    "Healthcare AI": (
        "healthcare ai", "medical ai", "clinical ai", "health informatics",
        "medical machine learning", "biomedicine",
    ),
    "Climate & Sustainability": (
        "climate", "sustainability", "environmental", "earth science", "energy systems",
        "remote sensing",
    ),
    "Education Technology": (
        "education technology", "educational technology", "learning sciences",
        "computer science education", "ai in education",
    ),
    "Cognitive Science": (
        "cognitive science", "cognition", "computational neuroscience", "psychology",
        "neuroscience", "brain",
    ),
}

AI_SUBFIELDS = {
    "Artificial Intelligence",
    "Machine Learning",
    "Deep Learning",
    "Reinforcement Learning",
    "Natural Language Processing",
    "Large Language Models",
    "Generative AI",
    "Computer Vision",
    "Robotics",
    "Autonomous Systems",
    "AI Safety",
    "Human-Centered AI",
    "Probabilistic Modeling",
    "Speech",
    "Information Retrieval",
}


def _contains_keyword(text: str, keyword: str) -> bool:
    if len(keyword) <= 4 and keyword.isalnum():
        return bool(re.search(rf"\b{re.escape(keyword)}\b", text))
    return keyword in text


def categorize_with_keywords(text: str) -> list[str]:
    lowered = " ".join(str(text).lower().replace("&", " and ").split())
    categories: list[str] = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(_contains_keyword(lowered, keyword) for keyword in keywords):
            categories.append(category)

    # Machine learning subfields should also be recognizable under broad ML/AI searches.
    if any(category in categories for category in {"Deep Learning", "Reinforcement Learning"}):
        if "Machine Learning" not in categories:
            categories.append("Machine Learning")
    if any(category in categories for category in AI_SUBFIELDS - {"Artificial Intelligence"}):
        if "Artificial Intelligence" not in categories:
            categories.append("Artificial Intelligence")

    return categories[:8] or ["Other Computing Research"]


def categorize_with_openai(text: str) -> list[str]:
    """Optional LLM categorization with a deterministic keyword fallback."""
    if not os.getenv("OPENAI_API_KEY"):
        return categorize_with_keywords(text)

    try:
        from openai import OpenAI

        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        allowed = ", ".join(CATEGORY_KEYWORDS)
        response = client.responses.create(
            model=model,
            store=False,
            input=(
                "Categorize the academic research interests below. Return only a JSON array "
                "with at most eight labels selected from this allowed list: "
                f"{allowed}. Include Artificial Intelligence when the work belongs to an AI "
                "subfield, and Machine Learning for deep or reinforcement learning.\n\n"
                f"Research interests: {text}"
            ),
        )
        parsed = json.loads(response.output_text)
        if isinstance(parsed, list):
            allowed_set = set(CATEGORY_KEYWORDS)
            cleaned = [str(item).strip() for item in parsed if str(item).strip() in allowed_set]
            if cleaned:
                return list(dict.fromkeys(cleaned))[:8]
    except Exception:
        pass

    return categorize_with_keywords(text)


def categories_to_text(categories: Iterable[str]) -> str:
    return ", ".join(
        dict.fromkeys(category.strip() for category in categories if category.strip())
    )
