import type {
  BrowserSessionRecord,
  BrowserSessionRecordStore,
  BrowserSessionKind,
  GripSessionStore,
  HydratedSession,
  NewSessionRequest,
  PersistedChange,
  RemoveSessionRequest,
  SessionSnapshot,
  SessionSummary,
  SyncCheckpoint,
} from "./types";

interface PersistedSessionRecord {
  session_id: string;
  summary: SessionSummary;
  snapshot: SessionSnapshot;
  applied_changes: PersistedChange[];
  pending_changes: PersistedChange[];
  sync_checkpoint: SyncCheckpoint;
}

interface IndexedDbGripSessionStoreOptions {
  databaseName?: string;
  objectStoreName?: string;
  browserSessionStoreName?: string;
  indexedDB?: IDBFactory;
}

function clone<T>(value: T): T {
  if (value === undefined || value === null) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}

function nowMs(): number {
  return Date.now();
}

function normalizeBrowserSessionRecord(record: BrowserSessionRecord): BrowserSessionRecord {
  return {
    ...record,
    session_kind: (record as BrowserSessionRecord & { session_kind?: BrowserSessionKind }).session_kind ?? "local",
  };
}

function createEmptySnapshot(sessionId?: string): SessionSnapshot {
  return { session_id: sessionId, contexts: {} };
}

function applyChangeToSnapshot(snapshot: SessionSnapshot, change: PersistedChange): void {
  const path = change.path;
  if (change.target_kind === "context") {
    if (change.payload) {
      snapshot.contexts[path] = {
        ...((change.payload as unknown) as SessionSnapshot["contexts"][string]),
        path,
      };
    }
    return;
  }
  if (change.target_kind === "child-order") {
    const context = snapshot.contexts[path];
    if (!context) return;
    context.children = [...((change.payload?.children as string[] | undefined) ?? [])];
    return;
  }
  if (change.target_kind === "drip") {
    const context = snapshot.contexts[path];
    if (!context || !change.grip_id) return;
    const payload = (change.payload ?? {}) as Record<string, unknown>;
    context.drips[change.grip_id] = {
      ...(context.drips[change.grip_id] ?? {
        grip_id: change.grip_id,
        name: change.grip_id,
        taps: [],
      }),
      ...payload,
      grip_id: change.grip_id,
    } as SessionSnapshot["contexts"][string]["drips"][string];
    return;
  }
  if (change.target_kind === "tap-meta") {
    const context = snapshot.contexts[path];
    if (!context || !change.grip_id) return;
    const drip = context.drips[change.grip_id];
    if (!drip) return;
    drip.taps = clone((change.payload?.taps as typeof drip.taps | undefined) ?? []);
    return;
  }
  if (change.target_kind === "remove") {
    if (!change.grip_id) {
      delete snapshot.contexts[path];
      return;
    }
    snapshot.contexts[path]?.drips && delete snapshot.contexts[path].drips[change.grip_id];
  }
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionToPromise(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

export class IndexedDbGripSessionStore implements GripSessionStore, BrowserSessionRecordStore {
  private readonly databaseName: string;
  private readonly objectStoreName: string;
  private readonly browserSessionStoreName: string;
  private readonly indexedDB: IDBFactory;
  private dbPromise?: Promise<IDBDatabase>;

  constructor(opts?: IndexedDbGripSessionStoreOptions) {
    this.databaseName = opts?.databaseName ?? "glial-local";
    this.objectStoreName = opts?.objectStoreName ?? "sessions";
    this.browserSessionStoreName = opts?.browserSessionStoreName ?? "browser_sessions";
    if (!opts?.indexedDB && !globalThis.indexedDB) {
      throw new Error("indexedDB is not available in this environment");
    }
    this.indexedDB = opts?.indexedDB ?? globalThis.indexedDB;
  }

  async newSession(request: NewSessionRequest): Promise<SessionSummary> {
    const session_id = request.session_id ?? `session_${Math.random().toString(36).slice(2, 10)}`;
    const summary: SessionSummary = {
      session_id,
      title: request.title,
      mode: "local",
      last_modified_ms: nowMs(),
    };
    const record: PersistedSessionRecord = {
      session_id,
      summary,
      snapshot: clone(request.initial_snapshot ?? createEmptySnapshot(session_id)),
      applied_changes: [],
      pending_changes: [],
      sync_checkpoint: { attached: false },
    };
    await this.putRecord(record);
    return clone(summary);
  }

  async listSessions(): Promise<SessionSummary[]> {
    const db = await this.getDb();
    const tx = db.transaction(this.objectStoreName, "readonly");
    const records = await requestToPromise(
      tx.objectStore(this.objectStoreName).getAll(),
    ) as PersistedSessionRecord[];
    await transactionToPromise(tx);
    return records.map((record) => clone(record.summary)).sort((a, b) => b.last_modified_ms - a.last_modified_ms);
  }

  async getSession(session_id: string): Promise<SessionSummary | null> {
    const record = await this.getRecord(session_id);
    return clone(record?.summary ?? null);
  }

  async listBrowserSessions(): Promise<BrowserSessionRecord[]> {
    const db = await this.getDb();
    const tx = db.transaction(this.browserSessionStoreName, "readonly");
    const records = await requestToPromise(
      tx.objectStore(this.browserSessionStoreName).getAll(),
    ) as BrowserSessionRecord[];
    await transactionToPromise(tx);
    return records
      .map((record) => normalizeBrowserSessionRecord(clone(record)))
      .sort((a, b) => b.last_opened_ms - a.last_opened_ms);
  }

  async getBrowserSession(browser_session_id: string): Promise<BrowserSessionRecord | null> {
    const db = await this.getDb();
    const tx = db.transaction(this.browserSessionStoreName, "readonly");
    const record = await requestToPromise(
      tx.objectStore(this.browserSessionStoreName).get(browser_session_id),
    ) as BrowserSessionRecord | undefined;
    await transactionToPromise(tx);
    return record ? normalizeBrowserSessionRecord(clone(record)) : null;
  }

  async putBrowserSession(record: BrowserSessionRecord): Promise<void> {
    const db = await this.getDb();
    const tx = db.transaction(this.browserSessionStoreName, "readwrite");
    tx.objectStore(this.browserSessionStoreName).put(clone(normalizeBrowserSessionRecord(record)));
    await transactionToPromise(tx);
  }

  async removeBrowserSession(browser_session_id: string): Promise<void> {
    const db = await this.getDb();
    const tx = db.transaction(this.browserSessionStoreName, "readwrite");
    tx.objectStore(this.browserSessionStoreName).delete(browser_session_id);
    await transactionToPromise(tx);
  }

  async hydrate(session_id: string): Promise<HydratedSession> {
    const record = await this.requireRecord(session_id);
    return {
      summary: clone(record.summary),
      snapshot: clone(record.snapshot),
      applied_changes: clone(record.applied_changes),
      pending_changes: clone(record.pending_changes),
      sync_checkpoint: clone(record.sync_checkpoint),
    };
  }

  async writeIncrementalChange(session_id: string, change: PersistedChange): Promise<void> {
    const record = await this.requireRecord(session_id);
    const nextChange = clone(change);
    if (nextChange.status === "pending_sync") {
      record.pending_changes = record.pending_changes.filter((entry) => entry.change_id !== nextChange.change_id);
      record.pending_changes.push(nextChange);
    } else {
      record.pending_changes = record.pending_changes.filter((entry) => entry.change_id !== nextChange.change_id);
      record.applied_changes.push(nextChange);
    }
    applyChangeToSnapshot(record.snapshot, nextChange);
    record.summary.last_modified_ms = nowMs();
    await this.putRecord(record);
  }

  async replaceSnapshot(
    session_id: string,
    snapshot: SessionSnapshot,
    _reason: "collapse" | "glial_resync" | "share_seed",
  ): Promise<void> {
    const record = await this.requireRecord(session_id);
    record.snapshot = clone(snapshot);
    record.snapshot.session_id ??= session_id;
    record.applied_changes = [];
    record.summary.last_modified_ms = nowMs();
    if (record.snapshot.snapshot_clock) {
      record.sync_checkpoint.last_snapshot_clock = clone(record.snapshot.snapshot_clock);
    }
    await this.putRecord(record);
  }

  async collapse(session_id: string): Promise<void> {
    const record = await this.requireRecord(session_id);
    record.applied_changes = [];
    record.summary.last_modified_ms = nowMs();
    await this.putRecord(record);
  }

  async removeSession(request: RemoveSessionRequest): Promise<void> {
    const db = await this.getDb();
    const tx = db.transaction(this.objectStoreName, "readwrite");
    tx.objectStore(this.objectStoreName).delete(request.session_id);
    await transactionToPromise(tx);
  }

  private async getRecord(session_id: string): Promise<PersistedSessionRecord | null> {
    const db = await this.getDb();
    const tx = db.transaction(this.objectStoreName, "readonly");
    const record = await requestToPromise(
      tx.objectStore(this.objectStoreName).get(session_id),
    ) as PersistedSessionRecord | undefined;
    await transactionToPromise(tx);
    return record ?? null;
  }

  private async requireRecord(session_id: string): Promise<PersistedSessionRecord> {
    const record = await this.getRecord(session_id);
    if (!record) {
      throw new Error(`Unknown session: ${session_id}`);
    }
    return record;
  }

  private async putRecord(record: PersistedSessionRecord): Promise<void> {
    const db = await this.getDb();
    const tx = db.transaction(this.objectStoreName, "readwrite");
    tx.objectStore(this.objectStoreName).put(record);
    await transactionToPromise(tx);
  }

  private async getDb(): Promise<IDBDatabase> {
    if (!this.dbPromise) {
      this.dbPromise = new Promise((resolve, reject) => {
        const request = this.indexedDB.open(this.databaseName, 2);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(this.objectStoreName)) {
            db.createObjectStore(this.objectStoreName, { keyPath: "session_id" });
          }
          if (!db.objectStoreNames.contains(this.browserSessionStoreName)) {
            db.createObjectStore(this.browserSessionStoreName, { keyPath: "browser_session_id" });
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    }
    return this.dbPromise;
  }
}
