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

export interface HttpGlialClientOptions {
  baseUrl: string;
  fetchImpl?: typeof fetch;
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

  constructor(opts: HttpGlialClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.fetchImpl = opts.fetchImpl ?? fetch;
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
