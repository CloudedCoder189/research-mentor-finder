import { RESEARCHERS } from "@/data/researchers";

export const UNIVERSITY_OPTIONS: string[] = Array.from(
  new Set(RESEARCHERS.map((r) => r.university)),
).sort();

export const STATE_OPTIONS: string[] = Array.from(
  new Set(RESEARCHERS.map((r) => r.state)),
).sort();

export const FIELD_OPTIONS: string[] = Array.from(
  new Set(RESEARCHERS.map((r) => r.field)),
).sort();

export const VERIFICATION_OPTIONS = [
  "Verified",
  "Review",
  "Failed",
  "Not checked",
] as const;

export const OPPORTUNITY_OPTIONS = ["Moderate or strong", "Strong only"] as const;

export const INTEREST_OPTIONS: string[] = [
  "Machine learning",
  "Human-Computer Interaction",
  "Robotics",
  "Computational biology",
  "Biomedical engineering",
  "Statistics",
  "Renewable energy",
  "Computational neuroscience",
  "Computer systems",
  "Materials science",
  "Algorithms",
  "Climate and the environment",
  "Astronomy and astrophysics",
  "Economics",
  "Quantum computing",
];

export const SKILL_OPTIONS: string[] = [
  "Python",
  "Pytorch",
  "TensorFlow",
  "React",
  "TypeScript",
  "C++",
  "Java",
  "R",
  "MATLAB",
  "Data analysis",
  "Statistical modeling",
  "Web development",
  "Prototyping",
  "Scientific writing",
  "Literature review",
  "Laboratory techniques",
  "Survey design",
  "Excel",
  "GIS",
];

export const COURSEWORK_OPTIONS: string[] = [
  "Biology",
  "Chemistry",
  "Physics",
  "Environmental Science",
  "Psychology",
  "Economics",
  "History",
  "Calculus",
  "Algorithms",
  "Machine Learning",
  "Human-Computer Interaction",
  "Statistics",
  "Linear Algebra",
  "Computer Architecture",
  "Operating Systems",
  "Data Structures",
  "Artificial Intelligence",
  "Probability",
];

export const UNIVERSITY_TYPE_OPTIONS: string[] = [
  "R1 university",
  "Large public university",
  "Small liberal arts college",
  "Any",
];

export const SUPPORT_LEVEL_OPTIONS: string[] = [
  "Open to undergrad outreach",
  "Mentored independent research",
  "Hands-on in-lab",
  "No preference",
];

export const COUNTRY_OPTIONS = ["United States"] as const;