export interface ResearchDirection {
  id: string;
  title: string;
  keywords: string[];
  query: string;
  question: string;
  approach: string;
  terms: { term: string; meaning: string }[];
  activity: string;
  steps: string[];
  materials: string;
  reflection: string;
  source: { label: string; url: string };
}

// Editorial learning guides, not claims about a particular lab's methods or openings.
export const RESEARCH_DIRECTIONS: ResearchDirection[] = [
  {
    id: "environment", title: "Environment and climate data",
    keywords: ["climate", "flood", "rain", "weather", "environment", "water", "sustainability", "satellite", "earth"],
    query: "climate environmental data", question: "How do changes in our environment affect people and ecosystems?",
    approach: "Environmental researchers may compare observations over time, build models, or study physical processes. The appropriate method depends on the question and available evidence.",
    terms: [{ term: "Remote sensing", meaning: "Studying something using measurements collected from a distance, often by satellites." }, { term: "Time series", meaning: "Measurements recorded in time order; differences can reflect real changes or how measurements were collected." }],
    activity: "Explore an Earth-science contribution",
    steps: ["Choose an Earth-science activity in NASA's project directory and read its instructions.", "Try its introductory task if its requirements suit you; do not collect new field data before reviewing its guidance.", "Describe what was observed, what was inferred, and one source of uncertainty."],
    materials: "Browser; some project activities require additional equipment or supervision.",
    reflection: "What would you need to know before comparing observations from two locations?",
    source: { label: "NASA citizen-science projects", url: "https://science.nasa.gov/citizen-science/" },
  },
  {
    id: "robotics", title: "Robotics and physical computing",
    keywords: ["robot", "robotics", "arduino", "sensor", "electronics", "mechanical", "bicycle", "drone", "automation"],
    query: "robotics sensors control", question: "How can a machine sense its surroundings and respond reliably?",
    approach: "Robotics can involve sensing, mechanical design, software and control. A model or small learning experiment can help you investigate one component before attempting a complete robot.",
    terms: [{ term: "Sensor", meaning: "A device that converts a physical condition into a measurement." }, { term: "Feedback control", meaning: "Adjusting an action using measurements of what actually happened." }],
    activity: "Choose a manageable engineering question",
    steps: ["Browse a beginner engineering project and check its materials, prerequisites and safety instructions.", "Identify the input you would change and the outcome you would measure.", "Discuss an appropriate learning activity with a teacher before building or modifying hardware."],
    materials: "Depends on the chosen project; review cost and equipment before committing.",
    reflection: "How would you tell whether a change helped, rather than the sensor simply producing different readings?",
    source: { label: "Science Buddies project-feasibility guide", url: "https://www.sciencebuddies.org/science-fair-projects/student-workbook/beginner/find-a-project-idea" },
  },
  {
    id: "health", title: "Biology and biomedical questions",
    keywords: ["biology", "biomedical", "cancer", "medicine", "health", "gene", "genetics", "cell", "drug", "biomaterials", "neuroscience", "brain", "brains"],
    query: "biomedical biology", question: "How do biological processes work, and what evidence could help us understand disease?",
    approach: "A biological question might involve existing datasets, observations or supervised laboratory experiments. A promising model or laboratory finding does not automatically establish a medical benefit.",
    terms: [{ term: "Model system", meaning: "A simplified system used to study a question; it may not behave exactly like a person." }, { term: "Association", meaning: "Two measurements vary together; this alone does not show that one causes the other." }],
    activity: "Practice distinguishing a question from a claim",
    steps: ["Find a biology or medicine project on Zooniverse and read what its research team asks volunteers to do.", "Try a tutorial if suitable, using only the activity's supplied material.", "Write down the contribution you made and what it cannot establish; do not collect personal medical information."],
    materials: "Browser for an appropriate online activity; no laboratory materials required for this learning route.",
    reflection: "What further evidence would be needed before applying a finding to people?",
    source: { label: "Zooniverse participation guide", url: "https://www.zooniverse.org/about" },
  },
  {
    id: "space", title: "Astronomy and space observations",
    keywords: ["space", "star", "stars", "planet", "planets", "astronomy", "exoplanet", "galaxy", "galaxies", "telescope", "astrophysics"],
    query: "astronomy exoplanets", question: "What can light and other observations tell us about distant objects?",
    approach: "Astronomers combine observations with physical models. Classifying supplied observations is one way to encounter authentic data without owning a telescope.",
    terms: [{ term: "Light curve", meaning: "A record of how an object's measured brightness changes over time." }, { term: "Spectrum", meaning: "Light separated by wavelength, which can provide information about a source." }],
    activity: "Try an astronomy classification tutorial",
    steps: ["Choose a current astronomy project from NASA's citizen-science directory.", "Read its tutorial and attempt a suitable sample task.", "Record a case that was hard to classify and explain why you were uncertain."],
    materials: "Browser for selected online activities; check the individual project's requirements.",
    reflection: "Why might several volunteers examine the same observation?",
    source: { label: "NASA citizen-science projects", url: "https://science.nasa.gov/citizen-science/" },
  },
  {
    id: "computing", title: "Computing and data analysis",
    keywords: ["computer", "computing", "coding", "code", "python", "algorithm", "algorithms", "machine learning", "artificial intelligence", "software", "statistics", "data science"],
    query: "machine learning algorithms", question: "How can we evaluate whether a computational approach works, and when it fails?",
    approach: "Computational research can compare methods on suitable data and inspect mistakes. Performance on one dataset does not prove that a method will work everywhere.",
    terms: [{ term: "Baseline", meaning: "A simple comparison method used to judge whether a more complicated method helps." }, { term: "Data leakage", meaning: "Information improperly reaching an evaluation, making performance look better than it is." }],
    activity: "Design a fair comparison before coding",
    steps: ["Choose a small, teacher-reviewed computing learning activity from a project guide.", "Identify a simple baseline and a measurement you would use for comparison.", "Write down what data you would need and what must remain separate during evaluation."],
    materials: "Browser or spreadsheet initially; coding requirements depend on the activity you choose.",
    reflection: "What would make a comparison unfair even if the final accuracy looked impressive?",
    source: { label: "Science Buddies project-feasibility guide", url: "https://www.sciencebuddies.org/science-fair-projects/student-workbook/beginner/find-a-project-idea" },
  },
  {
    id: "humanities", title: "History, language and archival research",
    keywords: ["history", "historical", "humanities", "language", "linguistics", "literature", "art", "archive", "archives", "culture", "music"],
    query: "history language humanities", question: "What do records and cultural works reveal, and whose perspectives might be missing?",
    approach: "Researchers interpret sources in context, compare accounts and examine gaps. Archival transcription is a contribution to access, distinct from completing an original historical study.",
    terms: [{ term: "Primary source", meaning: "Material originating from the period or event under study; it still requires critical interpretation." }, { term: "Provenance", meaning: "Where a source came from and the context of its creation and preservation." }],
    activity: "Explore an archival record",
    steps: ["Read the National Archives getting-started and contribution guidance.", "Explore a record; try a suitable transcription task if you meet its account requirements.", "Separate what the record states from your interpretation, and note a question it leaves unanswered."],
    materials: "Browser; check registration and contribution requirements on the provider's site.",
    reflection: "Whose perspective is present in this record, and whose might not be recorded?",
    source: { label: "National Archives Citizen Archivist", url: "https://www.archives.gov/citizen-archivist" },
  },
  {
    id: "behavior", title: "Learning and human behavior",
    keywords: ["psychology", "behavior", "behaviour", "human learning", "student learning", "learning sciences", "memory", "education", "social", "mental health", "decision", "decisions"],
    query: "psychology learning memory", question: "How do people learn, think and make decisions?",
    approach: "Behavioral researchers need carefully defined measurements and appropriate study designs. Collecting information from people may require approval before work begins.",
    terms: [{ term: "Confounder", meaning: "Another factor that could help explain an apparent relationship." }, { term: "Operational definition", meaning: "A precise description of how an idea will be measured in a study." }],
    activity: "Turn an everyday observation into a question",
    steps: ["Choose a learning or behavior question you care about.", "Find background guidance and define what you mean by the main terms.", "Discuss possible designs and required approvals with a teacher; do not start a survey or experiment on people from this guide."],
    materials: "Reading and a conversation with an adult sponsor; no participant data collection in this activity.",
    reflection: "Could another explanation account for the observation you noticed?",
    source: { label: "Society for Science project rules", url: "https://www.societyforscience.org/isef/international-rules/rules-for-all-projects/" },
  },
];
