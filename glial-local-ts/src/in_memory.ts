import {
  ContextState,
  EnableSharingRequest,
  GripSessionLink,
  GripSessionPersistence,
  GripSessionStore,
  HydratedSession,
  NewSessionRequest,
  PersistedChange,
  PersistenceEvent,
  RemoveSessionRequest,
  SessionSnapshot,
  SessionSummary,
  SharingState,
  SyncCheckpoint,
} from "./types";

interface SessionRecord {
  summary: SessionSummary;
  snapshot: SessionSnapshot;
  applied_changes: PersistedChange[];
  pending_changes: PersistedChange[];
  sync_checkpoint: SyncCheckpoint;
  sharing_state: SharingState;
  subscribers: Set<(event: PersistenceEvent) => void>;
}

function clone<T>(value: T): T {
  if (value === undefined || value === null) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}

function nowMs(): number {
  return Date.now();
}

function createEmptySnapshot(sessionId?: string): SessionSnapshot {
  return { session_id: sessionId, contexts: {} };
}

function applyChangeToSnapshot(snapshot: SessionSnapshot, change: PersistedChange): void {
  const path = change.path;
  if (change.target_kind === "context") {
    const context = clone(change.payload as ContextState | undefined);
    if (context) {
      snapshot.contexts[path] = { ...context, path };
    }
    return;
  }

  if (change.target_kind === "child-order") {
    const context = snapshot.contexts[path];
    if (!context) return;
    const children = (change.payload?.children as string[] | undefined) ?? [];
    context.children = [...children];
    return;
  }

  if (change.target_kind === "drip") {
    const context = snapshot.contexts[path];
    if (!context || !change.grip_id) return;
    const drip = clone(change.payload ?? {});
    context.drips[change.grip_id] = {
      ...(context.drips[change.grip_id] ?? {
        grip_id: change.grip_id,
        name: change.grip_id,
        taps: [],
      }),
      ...(drip as Record<string, unknown>),
      grip_id: change.grip_id,
    };
    return;
  }

  if (change.target_kind === "tap-meta") {
    const context = snapshot.contexts[path];
    if (!context || !change.grip_id) return;
    const drip = context.drips[change.grip_id];
    if (!drip) return;
    const taps = (change.payload?.taps as typeof drip.taps | undefined) ?? [];
    drip.taps = clone(taps);
    return;
  }

  if (change.target_kind === "remove") {
    if (!change.grip_id) {
      delete snapshot.contexts[path];
      return;
    }
    const context = snapshot.contexts[path];
    if (!context) return;
    delete context.drips[change.grip_id];
  }
}

export class InMemoryGripSessionStore implements GripSessionStore {
  private readonly sessions = new Map<string, SessionRecord>();

  async newSession(request: NewSessionRequest): Promise<SessionSummary> {
    const session_id = request.session_id ?? `session_${Math.random().toString(36).slice(2, 10)}`;
    const summary: SessionSummary = {
      session_id,
      title: request.title,
      mode: "local",
      last_modified_ms: nowMs(),
    };
    const record: SessionRecord = {
      summary,
      snapshot: clone(request.initial_snapshot ?? createEmptySnapshot(session_id)),
      applied_changes: [],
      pending_changes: [],
      sync_checkpoint: { attached: false },
      sharing_state: "detached",
      subscribers: new Set(),
    };
    this.sessions.set(session_id, record);
    return clone(summary);
  }

  async listSessions(): Promise<SessionSummary[]> {
    return Array.from(this.sessions.values())
      .map((record) => clone(record.summary))
      .sort((a, b) => b.last_modified_ms - a.last_modified_ms);
  }

  async getSession(session_id: string): Promise<SessionSummary | null> {
    return clone(this.sessions.get(session_id)?.summary ?? null);
  }

  async hydrate(session_id: string): Promise<HydratedSession> {
    const record = this.requireSession(session_id);
    return this.cloneHydrated(record);
  }

  async writeIncrementalChange(session_id: string, change: PersistedChange): Promise<void> {
    const record = this.requireSession(session_id);
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
    this.emit(record, { kind: "delta", change: clone(nextChange) });
  }

  async replaceSnapshot(
    session_id: string,
    snapshot: SessionSnapshot,
    _reason: "collapse" | "glial_resync" | "share_seed",
  ): Promise<void> {
    const record = this.requireSession(session_id);
    record.snapshot = clone(snapshot);
    record.snapshot.session_id ??= session_id;
    record.applied_changes = [];
    record.summary.last_modified_ms = nowMs();
    if (snapshot.snapshot_clock) {
      record.sync_checkpoint.last_snapshot_clock = clone(snapshot.snapshot_clock);
    }
    this.emit(record, {
      kind: "snapshot_reset",
      snapshot: clone(record.snapshot),
      checkpoint: clone(record.sync_checkpoint),
    });
  }

  async collapse(session_id: string): Promise<void> {
    const record = this.requireSession(session_id);
    record.applied_changes = [];
    record.summary.last_modified_ms = nowMs();
  }

  async removeSession(request: RemoveSessionRequest): Promise<void> {
    this.sessions.delete(request.session_id);
  }

  protected requireSession(session_id: string): SessionRecord {
    const record = this.sessions.get(session_id);
    if (!record) {
      throw new Error(`Unknown session: ${session_id}`);
    }
    return record;
  }

  protected cloneHydrated(record: SessionRecord): HydratedSession {
    return {
      summary: clone(record.summary),
      snapshot: clone(record.snapshot),
      applied_changes: clone(record.applied_changes),
      pending_changes: clone(record.pending_changes),
      sync_checkpoint: clone(record.sync_checkpoint),
    };
  }

  protected emit(record: SessionRecord, event: PersistenceEvent): void {
    for (const sink of record.subscribers) {
      sink(clone(event));
    }
  }

  subscribe(session_id: string, sink: (event: PersistenceEvent) => void): () => void {
    const record = this.requireSession(session_id);
    record.subscribers.add(sink);
    return () => {
      record.subscribers.delete(sink);
    };
  }

  setSharingState(session_id: string, state: SharingState): void {
    const record = this.requireSession(session_id);
    record.sharing_state = state;
    this.emit(record, { kind: "sharing_state", session_id, state });
  }

  setSessionMode(session_id: string, mode: SessionSummary["mode"]): void {
    const record = this.requireSession(session_id);
    record.summary.mode = mode;
    record.summary.last_modified_ms = nowMs();
  }
}

export class NullGripSessionLink implements GripSessionLink {
  async attach(_request: EnableSharingRequest): Promise<void> {}
  async detach(_session_id: string): Promise<void> {}
  async publishLocalChange(_session_id: string, _change: PersistedChange): Promise<void> {}
}

export class InMemoryGripSessionPersistence implements GripSessionPersistence {
  constructor(
    private readonly store: InMemoryGripSessionStore = new InMemoryGripSessionStore(),
    private readonly link: GripSessionLink = new NullGripSessionLink(),
  ) {}

  async newSession(request: NewSessionRequest): Promise<SessionSummary> {
    return this.store.newSession(request);
  }

  async listSessions(): Promise<SessionSummary[]> {
    return this.store.listSessions();
  }

  async getSession(session_id: string): Promise<SessionSummary | null> {
    return this.store.getSession(session_id);
  }

  async hydrate(session_id: string): Promise<HydratedSession> {
    return this.store.hydrate(session_id);
  }

  async subscribe(
    session_id: string,
    sink: (event: PersistenceEvent) => void,
  ): Promise<() => void> {
    return this.store.subscribe(session_id, sink);
  }

  async writeIncrementalChange(session_id: string, change: PersistedChange): Promise<void> {
    await this.store.writeIncrementalChange(session_id, change);
    if (change.source === "local" && change.status === "pending_sync") {
      await this.link.publishLocalChange(session_id, change);
    }
  }

  async replaceSnapshot(
    session_id: string,
    snapshot: SessionSnapshot,
    reason: "collapse" | "glial_resync" | "share_seed",
  ): Promise<void> {
    await this.store.replaceSnapshot(session_id, snapshot, reason);
  }

  async collapse(session_id: string): Promise<void> {
    await this.store.collapse(session_id);
  }

  async enableSharing(request: EnableSharingRequest): Promise<void> {
    this.store.setSessionMode(request.session_id, "shared");
    this.store.setSharingState(request.session_id, "attaching");
    await this.link.attach(request);
    this.store.setSharingState(request.session_id, "live");
  }

  async disableSharing(session_id: string): Promise<void> {
    await this.link.detach(session_id);
    this.store.setSharingState(session_id, "detached");
    this.store.setSessionMode(session_id, "local");
  }

  async removeSession(request: RemoveSessionRequest): Promise<void> {
    if (request.scope === "local_and_shared") {
      await this.link.detach(request.session_id);
    }
    await this.store.removeSession(request);
  }
}
