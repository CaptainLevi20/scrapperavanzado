// A run stops changing once it reaches "completed", "failed", or "cancelled" —
// polling and the cancel button both need to treat any of these as done, not
// just "completed".
export function isTerminalRunStatus(status: string): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

// A worker process that dies outright (OOM-killed, container restarted, host
// rebooted) never gets a chance to write "failed" — the run just stays
// "running" (or even "pending") in the database forever. Without a cutoff,
// polling every few seconds would continue for as long as the tab stays
// open. 30 minutes is comfortably longer than any real run this project has
// seen; past that, stop guessing and let the user refresh manually instead.
export const MAX_POLL_AGE_MS = 30 * 60 * 1000;

export function isStaleRun(createdAt: string, status: string, now = Date.now()): boolean {
  if (isTerminalRunStatus(status)) return false;
  return now - new Date(createdAt).getTime() > MAX_POLL_AGE_MS;
}

export function shouldPollRun(createdAt: string, status: string, now = Date.now()): boolean {
  return !isTerminalRunStatus(status) && !isStaleRun(createdAt, status, now);
}
