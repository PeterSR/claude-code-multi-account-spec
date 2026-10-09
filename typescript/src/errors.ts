/** Error codes defined by the spec (and the harness additions listed in conformance/FORMAT.md). */
export type ErrorCode =
  | "INVALID_NAME"
  | "RESERVED_NAME"
  | "ACCOUNT_NOT_FOUND"
  | "ACCOUNT_UNAVAILABLE"
  | "ACCOUNT_EXISTS"
  | "ENV_CONFLICT"
  | "MARKER_INVALID"
  | "CLAIM_CONFLICT"
  | "SPEC_FILE_INVALID"
  | "INVALID_SESSION_ID"
  | "SAME_ACCOUNT"
  | "SESSION_LIVE"
  | "SESSION_EXISTS"
  | "SESSION_NOT_FOUND"
  | "SLOT_UNSUPPORTED"
  | "SLOT_STATE"
  | "SLOT_CONFLICT"
  | "DESTINATION_BLOCKED"
  | "SLOT_TARGET_INVALID"
  | "STATE_FILE_INVALID"
  | "INVALID_ENTRY"
  | "LOCK_BUSY"
  | "IO_ERROR";

/** The one error type of the library: a spec code, a human message and, where relevant, a path. */
export class MultiAccountError extends Error {
  readonly code: ErrorCode;
  readonly path: string | null;

  constructor(code: ErrorCode, message?: string, path: string | null = null) {
    super(message ?? code);
    this.name = "MultiAccountError";
    this.code = code;
    this.path = path;
  }
}

/** Warning codes. Warnings never abort an operation. */
export type WarningCode =
  | "EMPTY_ENV"
  | "ENV_NOT_APPLIED"
  | "NON_CANONICAL_CONFIG_DIR"
  | "NOT_A_DIRECTORY"
  | "MARKER_IGNORED_IN_REPO"
  | "CANDIDATE_UNAVAILABLE"
  | "RESERVED_NAME";

/** A non-fatal finding. `path` is set when it concerns one file or directory. */
export interface Warning {
  code: WarningCode;
  message: string;
  path?: string;
}

/**
 * Runs `fn` and turns any unexpected filesystem error (anything with a string `code` that is not already a
 * MultiAccountError) into IO_ERROR with the path involved, so callers never see a raw platform error.
 */
export async function guarded<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (e instanceof MultiAccountError) throw e;
    if (typeof e === "object" && e !== null && typeof (e as { code?: unknown }).code === "string") {
      const p = (e as { path?: unknown }).path;
      throw new MultiAccountError("IO_ERROR", e instanceof Error ? e.message : String(e), typeof p === "string" ? p : null);
    }
    throw e;
  }
}
