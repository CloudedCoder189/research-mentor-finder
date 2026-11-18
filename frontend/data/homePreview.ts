import type { MatchLabel } from "@/types";

/**
 * Illustrative homepage preview rows.
 *
 * These are presentation-only examples (not live researcher records) used to show
 * the shape of a recommendation before sign-in. They intentionally carry no
 * researcher id, so no live Save/outreach operation can be started from them —
 * the Save control is inert and "View profile" routes to a real Discover search.
 */
export interface HomePreviewResearcher {
  id: string;
  name: string;
  university: string;
  department: string;
  topics: string[];
  matchLabel: MatchLabel;
  whyMatch: string;
  /** Live Discover query that surfaces real results for this example. */
  searchQuery: string;
}

export const HOME_PREVIEW_SAMPLE_INTERESTS = "robotics, Python, computer vision";

export const HOME_PREVIEW_RESEARCHERS: HomePreviewResearcher[] = [
  {
    id: "preview-dieter-fox",
    name: "Dieter Fox",
    university: "University of Washington",
    department: "Paul G. Allen School of Computer Science & Engineering",
    topics: ["robotics", "computer vision", "human-robot interaction"],
    matchLabel: "Strong research match",
    whyMatch:
      "Robotics and computer vision sit right in the middle of this researcher’s work, and Python is the language their open-source tools are built in.",
    searchQuery: "Dieter Fox robotics",
  },
  {
    id: "preview-jane-smith",
    name: "Professor Jane Smith",
    university: "Stanford University",
    department: "Computer Science",
    topics: ["machine learning", "computer vision", "responsible AI"],
    matchLabel: "Good research match",
    whyMatch:
      "This group publishes on machine learning and computer vision, so a Python background maps cleanly onto their courseware and research code.",
    searchQuery: "Jane Smith Stanford machine learning",
  },
  {
    id: "preview-alex-chen",
    name: "Professor Alex Chen",
    university: "University of California, Berkeley",
    department: "Electrical Engineering and Computer Sciences",
    topics: ["reinforcement learning", "robotics", "embedded systems"],
    matchLabel: "Possible match",
    whyMatch:
      "Reinforcement learning and robotics research overlaps with your interests, though the group leans more toward hardware than your current focus.",
    searchQuery: "Alex Chen Berkeley reinforcement learning",
  },
];
