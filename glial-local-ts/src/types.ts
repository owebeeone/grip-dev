export type SessionMode = "local" | "shared";
export type BrowserSessionStorageMode = "local" | "remote" | "both";
export type BrowserSessionKind = "local" | "glial-storage" | "glial-shared";
export type ChangeSource = "local" | "glial" | "hydrate" | "collapse";
export type ChangeStatus = "applied" | "pending_sync" | "confirmed" | "superseded";
export type PersistenceTargetKind = "context" | "child-order" | "drip" | "tap-meta" | "remove";
export type TapExecutionMode = "replicated" | "origin-primary" | "negotiated-primary";
export type TapExecutionRole = "primary" | "follower";

export interface VirtualClock {
  wall_time_ms: number;
  logical_counter: number;
  replica_id: string;
}

export interface TapExport {
  tap_id: string;
  tap_type: string;
  mode: TapExecutionMode | string;
  role?: TapExecutionRole | string;
  provides: string[];
  home_param_grips?: string[];
  destination_param_grips?: string[];
  purpose?: string;
  description?: string;
  metadata?: Record<string, unknown>;
  cache_state?: Record<string, unknown> | null;
}

export interface DripState {
  grip_id: string;
  name: string;
  value?: unknown;
  value_clock?: VirtualClock;
  purpose?: string;
  description?: string;
  taps: TapExport[];
}

export interface ContextState {
  path: string;
  name: string;
  purpose?: string;
  description?: string;
  entry_clock?: VirtualClock;
  children: string[];
  drips: Record<string, DripState>;
}

export interface SessionSnapshot {
  session_id?: string;
  snapshot_clock?: VirtualClock;
  contexts: Record<string, ContextState>;
}

export interface SessionSummary {
  session_id: string;
  title?: string;
  mode: SessionMode;
  last_modified_ms: number;
  last_glial_session_clock?: VirtualClock;
}

export interface BrowserSessionRecord {
  browser_session_id: string;
  glial_session_id: string;
  title?: string;
  storage_mode: BrowserSessionStorageMode;
  session_kind: BrowserSessionKind;
  last_opened_ms: number;
}

export interface SyncCheckpoint {
  attached: boolean;
  last_applied_clock?: VirtualClock;
  last_snapshot_clock?: VirtualClock;
  last_snapshot_id?: string;
}

export interface PersistedChange {
  change_id: string;
  session_id: string;
  source: ChangeSource;
  status: ChangeStatus;
  origin_replica_id?: string;
  origin_mutation_seq?: number;
  origin_generation?: number;
  session_clock?: VirtualClock;
  target_kind: PersistenceTargetKind;
  path: string;
  grip_id?: string;
  tap_id?: string;
  payload?: Record<string, unknown>;
}

export interface HydratedSession {
  summary: SessionSummary;
  snapshot: SessionSnapshot;
  applied_changes: PersistedChange[];
  pending_changes: PersistedChange[];
  sync_checkpoint: SyncCheckpoint;
}

export interface NewSessionRequest {
  session_id?: string;
  title?: string;
  initial_snapshot?: SessionSnapshot;
}

export interface EnableSharingRequest {
  session_id: string;
  mode: "share_local_session";
}

export interface RemoveSessionRequest {
  session_id: string;
  scope: "local_only" | "local_and_shared";
}

export type SharingState = "detached" | "attaching" | "live" | "resyncing" | "error";

export type PersistenceEvent =
  | { kind: "delta"; change: PersistedChange }
  | { kind: "snapshot_reset"; snapshot: SessionSnapshot; checkpoint: SyncCheckpoint }
  | { kind: "sharing_state"; session_id: string; state: SharingState };

export interface GripSessionPersistence {
  newSession(request: NewSessionRequest): Promise<SessionSummary>;
  listSessions(): Promise<SessionSummary[]>;
  getSession(session_id: string): Promise<SessionSummary | null>;
  hydrate(session_id: string): Promise<HydratedSession>;
  subscribe(session_id: string, sink: (event: PersistenceEvent) => void): Promise<() => void>;
  writeIncrementalChange(session_id: string, change: PersistedChange): Promise<void>;
  replaceSnapshot(
    session_id: string,
    snapshot: SessionSnapshot,
    reason: "collapse" | "glial_resync" | "share_seed",
  ): Promise<void>;
  collapse(session_id: string): Promise<void>;
  enableSharing(request: EnableSharingRequest): Promise<void>;
  disableSharing(session_id: string): Promise<void>;
  removeSession(request: RemoveSessionRequest): Promise<void>;
}

export interface GripSessionStore {
  newSession(request: NewSessionRequest): Promise<SessionSummary>;
  listSessions(): Promise<SessionSummary[]>;
  getSession(session_id: string): Promise<SessionSummary | null>;
  hydrate(session_id: string): Promise<HydratedSession>;
  writeIncrementalChange(session_id: string, change: PersistedChange): Promise<void>;
  replaceSnapshot(
    session_id: string,
    snapshot: SessionSnapshot,
    reason: "collapse" | "glial_resync" | "share_seed",
  ): Promise<void>;
  collapse(session_id: string): Promise<void>;
  removeSession(request: RemoveSessionRequest): Promise<void>;
}

export interface BrowserSessionRecordStore {
  listBrowserSessions(): Promise<BrowserSessionRecord[]>;
  getBrowserSession(browser_session_id: string): Promise<BrowserSessionRecord | null>;
  putBrowserSession(record: BrowserSessionRecord): Promise<void>;
  removeBrowserSession(browser_session_id: string): Promise<void>;
}

export interface GripSessionLink {
  attach(request: EnableSharingRequest): Promise<void>;
  detach(session_id: string): Promise<void>;
  publishLocalChange(session_id: string, change: PersistedChange): Promise<void>;
}
