import { apiFetch } from "@/lib/api/client";
import type {
  FullProfilePreferencesDto,
  StudentProfileDto,
  StudentProfileUpdateDto,
} from "@/lib/api/types";
import type { EducationLevel, StudentProfile } from "@/types";

export function getProfile(signal?: AbortSignal): Promise<StudentProfileDto> {
  return apiFetch<StudentProfileDto>("/api/profile", { signal });
}

export function saveProfile(update: StudentProfileUpdateDto): Promise<StudentProfileDto> {
  return apiFetch<StudentProfileDto>("/api/profile", {
    method: "PUT",
    body: update,
  });
}

/** Serialize the app profile to the wire format used by /api/profile. */
export function toStudentDto(profile: StudentProfile): StudentProfileUpdateDto {
  const preferences: FullProfilePreferencesDto = {
    locations: profile.preferences.locations,
    university_types: profile.preferences.universityTypes,
    support_level: profile.preferences.supportLevel,
    remote_ok: profile.preferences.remoteOk,
  };
  return {
    interests: profile.interests,
    interest_text: profile.interestText,
    skills: profile.skills,
    experience: profile.experience,
    coursework: profile.coursework,
    education_level: profile.education_level,
    preferences,
    completed: profile.completed,
  };
}

function toEducationLevel(value: string): EducationLevel {
  const level: EducationLevel[] = ["unspecified", "high_school", "college", "university", "graduate"];
  return level.includes(value as EducationLevel) ? (value as EducationLevel) : "unspecified";
}

/** Parse the wire format into the app profile. Resume stays client-local. */
export function fromStudentDto(dto: StudentProfileDto): StudentProfile {
  return {
    interests: dto.interests,
    interestText: dto.interest_text,
    skills: dto.skills,
    experience: dto.experience,
    coursework: dto.coursework,
    education_level: toEducationLevel(dto.education_level),
    preferences: {
      locations: dto.preferences.locations,
      universityTypes: dto.preferences.university_types,
      supportLevel: dto.preferences.support_level || "No preference",
      remoteOk: dto.preferences.remote_ok,
    },
    resume: { fileName: null },
    completed: dto.completed,
  };
}