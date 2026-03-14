import type {
  EnableSharingRequest,
  GripSessionLink,
  PersistedChange,
} from "../../glial-local-ts/src/types";

export interface GlialClock {
  wall_time_ms: number;
  logical_counter: number;
  replica_id: string;
}

export interface AttachSessionResponse {
  session_id: string;
  snapshot: Record<string, unknown>;
  last_clock: GlialClock;
}

export interface ReplayResponse {
  session_id: string;
  changes: PersistedChange[];
  last_clock: GlialClock;
}

export interface RemoteSessionSummary {
  session_id: string;
  title?: string;
  last_modified_ms: number;
}

export interface RemoteSessionLoadResponse {
  session_id: string;
  title?: string;
  snapshot: Record<string, unknown>;
  last_modified_ms: number;
}

export interface SharedSessionLoadResponse {
  session_id: string;
  title?: string;
  snapshot: Record<string, unknown>;
  leases: Record<string, Record<string, unknown>>;
  last_modified_ms: number;
}

export interface SharedSessionSubscriptionHandlers {
  onSnapshot?(session: SharedSessionLoadResponse): void;
  onError?(error: unknown): void;
  onOpen?(): void;
  onClose?(): void;
}

export interface SharedSessionSubscription {
  close(): void;
}

interface WebSocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  close(): void;
}

type WebSocketFactory = (url: string) => WebSocketLike;

export interface LeaseResponse {
  tap_id: string;
  primary_replica_id: string;
  priority: number;
  granted_ms: number;
  granted: boolean;
}

export interface HttpGlialClientOptions {
  baseUrl: string;
  fetchImpl?: typeof fetch;
  webSocketFactory?: WebSocketFactory;
}

async function requestJson<T>(
  fetchImpl: typeof fetch,
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetchImpl(input, init);
  if (!response.ok) {
    throw new Error(`Glial request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function requestNoContent(
  fetchImpl: typeof fetch,
  input: string,
  init?: RequestInit,
): Promise<void> {
  const response = await fetchImpl(input, init);
  if (!response.ok) {
    throw new Error(`Glial request failed: ${response.status}`);
  }
}

export class HttpGlialClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly webSocketFactory?: WebSocketFactory;

  constructor(opts: HttpGlialClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.fetchImpl = opts.fetchImpl ?? fetch;
    this.webSocketFactory = opts.webSocketFactory;
  }

  async attachSession(
    sessionId: string,
    snapshot?: Record<string, unknown>,
  ): Promise<AttachSessionResponse> {
    return requestJson<AttachSessionResponse>(
      this.fetchImpl,
      `${this.baseUrl}/sessions/${sessionId}/attach`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ snapshot: snapshot ?? null }),
      },
    );
  }

  async getSnapshot(sessionId: string): Promise<AttachSessionResponse> {
    return requestJson<AttachSessionResponse>(
      this.fetchImpl,
      `${this.baseUrl}/sessions/${sessionId}/snapshot`,
    );
  }

  async submitChange(sessionId: string, change: PersistedChange): Promise<PersistedChange> {
    const body = await requestJson<{ accepted_change: PersistedChange }>(
      this.fetchImpl,
      `${this.baseUrl}/sessions/${sessionId}/changes`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ change }),
      },
    );
    return body.accepted_change;
  }

  async replay(sessionId: string, sinceCounter = 0): Promise<ReplayResponse> {
    const url = new URL(`${this.baseUrl}/sessions/${sessionId}/replay`);
    url.searchParams.set("since_counter", String(sinceCounter));
    return requestJson<ReplayResponse>(this.fetchImpl, url.toString());
  }

  async listRemoteSessions(userId: string): Promise<RemoteSessionSummary[]> {
    const url = new URL(`${this.baseUrl}/remote-sessions`);
    url.searchParams.set("user_id", userId);
    return requestJson<RemoteSessionSummary[]>(this.fetchImpl, url.toString());
  }

  async loadRemoteSession(userId: string, sessionId: string): Promise<RemoteSessionLoadResponse> {
    const url = new URL(`${this.baseUrl}/remote-sessions/${sessionId}`);
    url.searchParams.set("user_id", userId);
    return requestJson<RemoteSessionLoadResponse>(this.fetchImpl, url.toString());
  }

  async saveRemoteSession(
    userId: string,
    sessionId: string,
    snapshot: Record<string, unknown>,
    title?: string,
  ): Promise<RemoteSessionLoadResponse> {
    const url = new URL(`${this.baseUrl}/remote-sessions/${sessionId}`);
    url.searchParams.set("user_id", userId);
    return requestJson<RemoteSessionLoadResponse>(this.fetchImpl, url.toString(), {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: title ?? null, snapshot }),
    });
  }

  async deleteRemoteSession(userId: string, sessionId: string): Promise<void> {
    const url = new URL(`${this.baseUrl}/remote-sessions/${sessionId}`);
    url.searchParams.set("user_id", userId);
    return requestNoContent(this.fetchImpl, url.toString(), {
      method: "DELETE",
    });
  }

  async loadSharedSession(userId: string, sessionId: string): Promise<SharedSessionLoadResponse> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}`);
    url.searchParams.set("user_id", userId);
    return requestJson<SharedSessionLoadResponse>(this.fetchImpl, url.toString());
  }

  async saveSharedSession(
    userId: string,
    sessionId: string,
    snapshot: Record<string, unknown>,
    title?: string,
  ): Promise<SharedSessionLoadResponse> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}`);
    url.searchParams.set("user_id", userId);
    return requestJson<SharedSessionLoadResponse>(this.fetchImpl, url.toString(), {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: title ?? null, snapshot }),
    });
  }

  async listSharedContexts(
    userId: string,
    sessionId: string,
  ): Promise<Record<string, unknown>> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}/contexts`);
    url.searchParams.set("user_id", userId);
    return requestJson<Record<string, unknown>>(this.fetchImpl, url.toString());
  }

  async listSharedTaps(userId: string, sessionId: string): Promise<Record<string, unknown>> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}/taps`);
    url.searchParams.set("user_id", userId);
    return requestJson<Record<string, unknown>>(this.fetchImpl, url.toString());
  }

  async listSharedLeases(userId: string, sessionId: string): Promise<Record<string, unknown>> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}/leases`);
    url.searchParams.set("user_id", userId);
    return requestJson<Record<string, unknown>>(this.fetchImpl, url.toString());
  }

  async requestTapLease(
    userId: string,
    sessionId: string,
    tapId: string,
    replicaId: string,
    priority = 0,
  ): Promise<LeaseResponse> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}/leases/${tapId}`);
    url.searchParams.set("user_id", userId);
    return requestJson<LeaseResponse>(this.fetchImpl, url.toString(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ replica_id: replicaId, priority }),
    });
  }

  async releaseTapLease(
    userId: string,
    sessionId: string,
    tapId: string,
    replicaId?: string,
  ): Promise<void> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}/leases/${tapId}`);
    url.searchParams.set("user_id", userId);
    if (replicaId) {
      url.searchParams.set("replica_id", replicaId);
    }
    return requestNoContent(this.fetchImpl, url.toString(), {
      method: "DELETE",
    });
  }

  async updateSharedValue(
    userId: string,
    sessionId: string,
    input: { path: string; grip_id: string; value: unknown },
  ): Promise<SharedSessionLoadResponse> {
    const url = new URL(`${this.baseUrl}/shared-sessions/${sessionId}/values`);
    url.searchParams.set("user_id", userId);
    return requestJson<SharedSessionLoadResponse>(this.fetchImpl, url.toString(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(input),
    });
  }

  subscribeSharedSession(
    userId: string,
    sessionId: string,
    handlers: SharedSessionSubscriptionHandlers,
    replicaId?: string,
  ): SharedSessionSubscription {
    const socket = this.createWebSocket(
      this.buildSharedSessionWebSocketUrl(
        userId,
        sessionId,
        replicaId ?? createReplicaId("shared-viewer"),
      ),
    );
    socket.onopen = (event) => {
      handlers.onOpen?.();
      void event;
    };
    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(String(event.data ?? "{}")) as
          | { type?: string; session?: SharedSessionLoadResponse; message?: string }
          | undefined;
        if (parsed?.type === "shared_session_snapshot" && parsed.session) {
          handlers.onSnapshot?.(parsed.session);
          return;
        }
        if (parsed?.type === "error") {
          handlers.onError?.(
            new Error(parsed.message ?? "Glial shared-session websocket error"),
          );
          return;
        }
        handlers.onError?.(
          new Error(`Unsupported Glial shared-session websocket event: ${parsed?.type ?? "unknown"}`),
        );
      } catch (error) {
        handlers.onError?.(error);
      }
    };
    socket.onerror = (event) => {
      handlers.onError?.(event);
    };
    socket.onclose = (event) => {
      handlers.onClose?.();
      void event;
    };
    return {
      close(): void {
        socket.close();
      },
    };
  }

  private buildSharedSessionWebSocketUrl(
    userId: string,
    sessionId: string,
    replicaId: string,
  ): string {
    const url = new URL(
      `/shared-sessions/${sessionId}/ws`,
      this.baseUrl.endsWith("/") ? this.baseUrl : `${this.baseUrl}/`,
    );
    if (url.protocol === "http:") {
      url.protocol = "ws:";
    } else if (url.protocol === "https:") {
      url.protocol = "wss:";
    }
    url.searchParams.set("user_id", userId);
    url.searchParams.set("replica_id", replicaId);
    return url.toString();
  }

  private createWebSocket(url: string): WebSocketLike {
    if (this.webSocketFactory) {
      return this.webSocketFactory(url);
    }
    if (typeof WebSocket === "undefined") {
      throw new Error("WebSocket is not available in this runtime");
    }
    return new WebSocket(url);
  }
}

export class HttpGripSessionLink implements GripSessionLink {
  private lastAcceptedChange: PersistedChange | undefined;
  private readonly client: HttpGlialClient;
  private readonly snapshotProvider?: (sessionId: string) => Record<string, unknown> | undefined;

  constructor(
    client: HttpGlialClient,
    snapshotProvider?: (sessionId: string) => Record<string, unknown> | undefined,
  ) {
    this.client = client;
    this.snapshotProvider = snapshotProvider;
  }

  getLastAcceptedChange(): PersistedChange | undefined {
    return this.lastAcceptedChange;
  }

  async attach(request: EnableSharingRequest): Promise<void> {
    await this.client.attachSession(
      request.session_id,
      this.snapshotProvider?.(request.session_id),
    );
  }

  async detach(_session_id: string): Promise<void> {}

  async publishLocalChange(
    session_id: string,
    change: PersistedChange,
  ): Promise<void> {
    this.lastAcceptedChange = await this.client.submitChange(session_id, change);
  }
}

function createReplicaId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}
