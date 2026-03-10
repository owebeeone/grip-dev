import type {
  BrowserSessionRecord,
  BrowserSessionRecordStore,
  BrowserSessionStorageMode,
  GripSessionStore,
  SessionSummary,
} from "./types";

export type GripSessionCatalog = GripSessionStore & BrowserSessionRecordStore;

function nowMs(): number {
  return Date.now();
}

export function createBrowserSessionId(prefix = "browser"): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

export async function ensureBrowserSessionRecord(
  store: GripSessionCatalog,
  browserSessionId: string,
  opts?: {
    title?: string;
    storageMode?: BrowserSessionStorageMode;
    glialSessionId?: string;
  },
): Promise<BrowserSessionRecord> {
  const existing = await store.getBrowserSession(browserSessionId);
  if (existing) {
    return existing;
  }
  const summary =
    opts?.glialSessionId
      ? ((await store.getSession(opts.glialSessionId)) ??
        (await store.newSession({
          session_id: opts.glialSessionId,
          title: opts.title,
        })))
      : await store.newSession({ title: opts?.title });
  const record: BrowserSessionRecord = {
    browser_session_id: browserSessionId,
    glial_session_id: summary.session_id,
    title: summary.title ?? opts?.title,
    storage_mode: opts?.storageMode ?? "local",
    last_opened_ms: nowMs(),
  };
  await store.putBrowserSession(record);
  return record;
}

export async function bindBrowserSessionToExistingSession(
  store: GripSessionCatalog,
  browserSessionId: string,
  session: SessionSummary,
  storageMode: BrowserSessionStorageMode = "local",
): Promise<BrowserSessionRecord> {
  const record: BrowserSessionRecord = {
    browser_session_id: browserSessionId,
    glial_session_id: session.session_id,
    title: session.title,
    storage_mode: storageMode,
    last_opened_ms: nowMs(),
  };
  await store.putBrowserSession(record);
  return record;
}
