"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_STUDENT_PROFILE } from "@/data/studentProfile";
import { useAuth } from "@/lib/auth-context";
import { fromStudentDto, getProfile, saveProfile as saveProfileRequest, toStudentDto } from "@/lib/api/profile";
import { ProfileSaveQueue } from "@/lib/profileSaveQueue";
import type { StudentProfile } from "@/types";

function resumeKey(userId: string): string { return `rmf:profile:resume:${userId}`; }
function readResume(userId: string): string | null {
  try { return window.localStorage.getItem(resumeKey(userId)); } catch { return null; }
}

export function useStudentProfile() {
  const { user, status: authStatus } = useAuth();
  const userId = user?.user_id;
  const [profile, setProfile] = useState<StudentProfile>(DEFAULT_STUDENT_PROFILE);
  const [profileAccount, setProfileAccount] = useState<string | undefined>(undefined);
  const [hydrated, setHydrated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const queue = useRef<ProfileSaveQueue<StudentProfile> | null>(null);
  const sequence = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const activeQueue = new ProfileSaveQueue<StudentProfile>(async (next) => {
      if (!userId) throw new Error("Sign in to save your profile.");
      await saveProfileRequest({ ...toStudentDto(next), expected_user_id: userId });
      // Never replace newer optimistic edits with an older server response.
    });
    queue.current = activeQueue;
    sequence.current += 1;
    setProfile(DEFAULT_STUDENT_PROFILE);
    setProfileAccount(userId);
    setHydrated(false);
    setSaving(false);
    setSaveError(null);
    if (authStatus === "ready") {
      if (!userId) {
        setHydrated(true);
      } else {
        getProfile(controller.signal).then((dto) => {
          if (cancelled) return;
          setProfile({ ...fromStudentDto(dto), resume: { fileName: readResume(userId) } });
          setHydrated(true);
        }).catch((cause) => {
          if (!cancelled) setSaveError(cause instanceof Error ? cause.message : "Could not load your profile.");
        });
      }
    }
    return () => {
      // Route navigation must not discard edits waiting behind an active PUT.
      // The server checks expected_user_id, so these cannot write to a new account.
      activeQueue.flush();
      queue.current = null;
      cancelled = true;
      controller.abort();
    };
  }, [userId, authStatus, loadAttempt]);

  const saveProfile = useCallback(async (next: StudentProfile): Promise<boolean> => {
    if (!userId || !hydrated || profileAccount !== userId || !queue.current) return false;
    const activeQueue = queue.current;
    const currentSequence = ++sequence.current;
    setProfile(next);
    setSaving(true);
    setSaveError(null);
    const saved = await activeQueue.save(next);
    if (queue.current === activeQueue && sequence.current === currentSequence) {
      setSaving(false);
      if (saved) {
        try {
          if (next.resume.fileName) window.localStorage.setItem(resumeKey(userId), next.resume.fileName);
          else window.localStorage.removeItem(resumeKey(userId));
        } catch { /* resume name is optional and device-local */ }
      } else {
        setSaveError("Your latest changes could not be saved. Check your connection and try again.");
      }
    }
    return saved && queue.current === activeQueue;
  }, [userId, hydrated, profileAccount]);

  const retryLoad = useCallback(() => setLoadAttempt((value) => value + 1), []);
  const ownsProfile = profileAccount === userId;
  const visibleProfile = ownsProfile ? profile : DEFAULT_STUDENT_PROFILE;
  const profileHydrated = ownsProfile && hydrated;
  const ready = profileHydrated && visibleProfile.interests.length > 0;
  return { profile: visibleProfile, saveProfile, hydrated: profileHydrated, ready, saving: ownsProfile && saving, saveError: ownsProfile ? saveError : null, retryLoad };
}
