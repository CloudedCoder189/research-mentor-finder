import type { StudentProfile } from "@/types";

export const DEFAULT_STUDENT_PROFILE: StudentProfile = {
  interests: [],
  interestText: "",
  skills: [],
  experience: [],
  coursework: [],
  education_level: "unspecified",
  preferences: {
    locations: [],
    universityTypes: [],
    supportLevel: "No preference",
    remoteOk: false,
  },
  resume: {
    fileName: null,
  },
  completed: false,
};

export function hasResearchInterests(profile: StudentProfile): boolean {
  return profile.interests.length > 0;
}