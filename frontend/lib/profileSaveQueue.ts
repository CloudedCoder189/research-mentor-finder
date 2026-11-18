/** Serialize full-profile writes; coalesce edits waiting behind an active save. */
export class ProfileSaveQueue<T> {
  private pending: { value: T; waiters: ((saved: boolean) => void)[] } | null = null;
  private running = false;
  private cancelled = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private write: (value: T) => Promise<void>, private delayMs = 250) {}

  save(value: T): Promise<boolean> {
    if (this.cancelled) return Promise.resolve(false);
    const result = new Promise<boolean>((resolve) => {
      const waiters = this.pending?.waiters ?? [];
      waiters.push(resolve);
      this.pending = { value, waiters };
    });
    if (!this.running) {
      if (this.timer) clearTimeout(this.timer);
      this.timer = setTimeout(() => { this.timer = null; void this.drain(); }, this.delayMs);
    }
    return result;
  }

  cancel(): void {
    this.cancelled = true;
    if (this.timer) clearTimeout(this.timer);
    this.pending?.waiters.forEach((resolve) => resolve(false));
    this.pending = null;
  }

  flush(): void {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (!this.running && this.pending && !this.cancelled) void this.drain();
  }

  private async drain(): Promise<void> {
    this.running = true;
    while (this.pending && !this.cancelled) {
      const batch = this.pending;
      this.pending = null;
      let saved = false;
      try { await this.write(batch.value); saved = !this.cancelled; } catch { /* caller displays the failure */ }
      batch.waiters.forEach((resolve) => resolve(saved));
    }
    this.running = false;
  }
}
