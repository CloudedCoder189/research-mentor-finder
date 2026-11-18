import type { Researcher, ResearcherMatch, StudentProfile } from "@/types";
import { firstName } from "@/lib/format";

export interface InterestKeywords {
  interest: string;
  keywords: string[];
  skillKeywords: string[];
}

export const INTEREST_KEYWORDS: InterestKeywords[] = [
  {
    interest: "Machine learning",
    keywords: [
      "machine learning",
      "deep learning",
      "artificial intelligence",
      "reinforcement learning",
      "computer vision",
      "natural language",
      "nlp",
      "learning algorithms",
    ],
    skillKeywords: ["python", "tensorflow", "pytorch", "scikit"],
  },
  {
    interest: "Human-Computer Interaction",
    keywords: ["human-computer interaction", "hci", "user interface", "usable", "accessibility"],
    skillKeywords: ["javascript", "typescript", "react", "prototyping", "frontend"],
  },
  {
    interest: "Robotics",
    keywords: ["robotics", "robot", "control systems", "autonomous", "manipulation", "mechatroni"],
    skillKeywords: ["c++", "ros", "cad"],
  },
  {
    interest: "Computational biology",
    keywords: ["computational biology", "bioinformatics", "genomics", "genetics", "proteomics"],
    skillKeywords: ["python", "r", "biology", "bioinformatics"],
  },
  {
    interest: "Biomedical engineering",
    keywords: [
      "biomedical",
      "bioengineering",
      "tissue engineering",
      "medical imaging",
      "neural engineering",
    ],
    skillKeywords: ["biotech", "signal processing", "engineering"],
  },
  {
    interest: "Statistics",
    keywords: ["statistics", "statistical", "probabili", "data analysis", "inference"],
    skillKeywords: ["r", "python", "sas", "statistics"],
  },
  {
    interest: "Renewable energy",
    keywords: ["energy", "renewable", "solar", "wind", "power system", "battery", "grid"],
    skillKeywords: ["python", "engineering", "circuits"],
  },
  {
    interest: "Computational neuroscience",
    keywords: ["neuroscience", "neural", "brain", "cognition", "vision"],
    skillKeywords: ["python", "matlab", "neuroscience"],
  },
  {
    interest: "Computer systems",
    keywords: [
      "systems",
      "operating systems",
      "distributed systems",
      "networking",
      "cloud",
      "security",
      "computer architecture",
    ],
    skillKeywords: ["c", "c++", "linux", "networking"],
  },
  {
    interest: "Materials science",
    keywords: ["materials", "nanomaterial", "ceramic", "polymer", "metallurgical"],
    skillKeywords: ["chemistry", "mechanical", "cad"],
  },
  {
    interest: "Algorithms",
    keywords: ["algorithm", "theory", "combinatorial", "optimization", "graph", "complexity", "game theory"],
    skillKeywords: ["python", "c++", "proofs"],
  },
  {
    interest: "Climate and the environment",
    keywords: ["climate", "environment", "sustainability", "ecology", "atmospheric", "watershed", "carbon"],
    skillKeywords: ["r", "python", "gis"],
  },
  {
    interest: "Astronomy and astrophysics",
    keywords: ["astronom", "astrophysics", "cosmology", "exoplanet", "galaxy", "stellar"],
    skillKeywords: ["python", "physics", "matlab"],
  },
  {
    interest: "Economics",
    keywords: ["economics", "economic", "econometrics", "market", "inequality", "development economics"],
    skillKeywords: ["r", "stata", "python", "economics"],
  },
  {
    interest: "Quantum computing",
    keywords: ["quantum", "qubit", "photonic", "superconducting"],
    skillKeywords: ["python", "physics", "linear algebra"],
  },
];

export function matchResearcher(researcher: Researcher, profile: StudentProfile): ResearcherMatch {
  const corpus = researcher.topics.join(" ").toLowerCase();
  const hitInterests: string[] = [];
  const skillHits: string[] = [];

  for (const entry of INTEREST_KEYWORDS) {
    const keywordHit = entry.keywords.some((k) => corpus.includes(k));
    const matchedSkill = entry.skillKeywords.find((k) =>
      profile.skills.some((skill) => skill.toLowerCase().includes(k)),
    );
    if (keywordHit) hitInterests.push(entry.interest);
    if (keywordHit && matchedSkill) skillHits.push(matchedSkill);
  }

  const score = hitInterests.length + skillHits.length;

  let label: ResearcherMatch["label"];
  if (score >= 3) label = "Strong match";
  else if (score === 2) label = "Good match";
  else if (score === 1) label = "Possible match";
  else label = "Limited match";

  const reasons: string[] = [];
  for (const interest of hitInterests.slice(0, 3)) {
    reasons.push(
      `You're interested in ${interest} — ${firstName(researcher.name)} works on it (${researcher.topics[0] ?? "related topics"}).`,
    );
  }
  if (skillHits.length > 0) {
    reasons.push(`Your hands-on experience with ${skillHits[0]} is a practical fit for this research area.`);
  }
  const wantsState =
    profile.preferences.locations.includes(researcher.state) ||
    profile.preferences.locations.includes("Anywhere");
  if (wantsState && reasons.length < 4) {
    reasons.push(`${researcher.university} is in ${researcher.state}, matching your preferred region.`);
  }
  const wantsOutreach = profile.preferences.supportLevel === "Open to undergrad outreach";
  if (
    wantsOutreach &&
    researcher.opportunityLevel !== "Basic" &&
    reasons.length < 4
  ) {
    reasons.push(`The profile publishes signals that researchers here are open to undergrad outreach.`);
  }
  if (reasons.length === 0) {
    reasons.push("Limited topic overlap right now — broaden your interests to surface better matches.");
  }

  return { label, score, reasons };
}