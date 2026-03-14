import { describe, expect, it, vi } from "vitest";
import { HttpGlialClient, HttpGripSessionLink } from "../src";
import type { PersistedChange } from "../../glial-local-ts/src/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  readonly url: string;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  emitOpen(): void {
    this.onopen?.(new Event("open"));
  }

  emitMessage(data: unknown): void {
    this.onmessage?.({
      data: typeof data === "string" ? data : JSON.stringify(data),
    } as MessageEvent);
  }

  emitError(): void {
    this.onerror?.(new Event("error"));
  }

  close(): void {
    this.closed = true;
    this.onclose?.(new Event("close") as CloseEvent);
  }
}

describe("HttpGlialClient", () => {
  it("attaches, submits changes, gets snapshots, and replays via fetch", async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        session_id: "session-a",
        snapshot: { session_id: "session-a", contexts: {} },
        last_clock: { wall_time_ms: 1, logical_counter: 0, replica_id: "glial" },
      }))
      .mockResolvedValueOnce(jsonResponse({
        accepted_change: {
          change_id: "change-1",
          session_id: "session-a",
          source: "local",
          status: "pending_sync",
          target_kind: "context",
          path: "/root",
          session_clock: { wall_time_ms: 2, logical_counter: 1, replica_id: "glial" },
        },
      }))
      .mockResolvedValueOnce(jsonResponse({
        session_id: "session-a",
        snapshot: { session_id: "session-a", contexts: { "/root": { path: "/root" } } },
        last_clock: { wall_time_ms: 2, logical_counter: 1, replica_id: "glial" },
      }))
      .mockResolvedValueOnce(jsonResponse({
        session_id: "session-a",
        changes: [{
          change_id: "change-1",
          session_id: "session-a",
          source: "local",
          status: "pending_sync",
          target_kind: "context",
          path: "/root",
        }],
        last_clock: { wall_time_ms: 2, logical_counter: 1, replica_id: "glial" },
      }));

    const client = new HttpGlialClient({
      baseUrl: "http://glial.test",
      fetchImpl: fetchMock,
    });
    const attach = await client.attachSession("session-a", { session_id: "session-a", contexts: {} });
    expect(attach.session_id).toBe("session-a");

    const accepted = await client.submitChange("session-a", {
      change_id: "change-1",
      session_id: "session-a",
      source: "local",
      status: "pending_sync",
      target_kind: "context",
      path: "/root",
    } as PersistedChange);
    expect(accepted.session_clock?.logical_counter).toBe(1);

    const snapshot = await client.getSnapshot("session-a");
    expect(snapshot.snapshot.session_id).toBe("session-a");

    const replay = await client.replay("session-a", 0);
    expect(replay.changes).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("uses snapshot provider and keeps last accepted change in the link", async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        session_id: "session-b",
        snapshot: { session_id: "session-b", contexts: {} },
        last_clock: { wall_time_ms: 1, logical_counter: 0, replica_id: "glial" },
      }))
      .mockResolvedValueOnce(jsonResponse({
        accepted_change: {
          change_id: "change-2",
          session_id: "session-b",
          source: "local",
          status: "pending_sync",
          target_kind: "drip",
          path: "/root",
          grip_id: "app:value",
          session_clock: { wall_time_ms: 2, logical_counter: 1, replica_id: "glial" },
        },
      }));

    const client = new HttpGlialClient({
      baseUrl: "http://glial.test",
      fetchImpl: fetchMock,
    });
    const link = new HttpGripSessionLink(client, (sessionId) => ({
      session_id: sessionId,
      contexts: {},
    }));

    await link.attach({ session_id: "session-b", mode: "share_local_session" });
    await link.publishLocalChange("session-b", {
      change_id: "change-2",
      session_id: "session-b",
      source: "local",
      status: "pending_sync",
      target_kind: "drip",
      path: "/root",
      grip_id: "app:value",
    } as PersistedChange);

    expect(link.getLastAcceptedChange()?.session_clock?.logical_counter).toBe(1);
  });

  it("lists, loads, and saves remote sessions via fetch", async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([
        {
          session_id: "session-remote-a",
          title: "Remote A",
          last_modified_ms: 100,
        },
      ]))
      .mockResolvedValueOnce(jsonResponse({
        session_id: "session-remote-a",
        title: "Remote A",
        snapshot: { session_id: "session-remote-a", contexts: {} },
        last_modified_ms: 100,
      }))
      .mockResolvedValueOnce(jsonResponse({
        session_id: "session-remote-a",
        title: "Remote A updated",
        snapshot: { session_id: "session-remote-a", contexts: { "/root": { path: "/root" } } },
        last_modified_ms: 200,
      }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const client = new HttpGlialClient({
      baseUrl: "http://glial.test",
      fetchImpl: fetchMock,
    });

    const listed = await client.listRemoteSessions("user-a");
    expect(listed).toHaveLength(1);

    const loaded = await client.loadRemoteSession("user-a", "session-remote-a");
    expect(loaded.session_id).toBe("session-remote-a");

    const saved = await client.saveRemoteSession(
      "user-a",
      "session-remote-a",
      { session_id: "session-remote-a", contexts: { "/root": { path: "/root" } } },
      "Remote A updated",
    );
    expect(saved.title).toBe("Remote A updated");

    await expect(client.deleteRemoteSession("user-a", "session-remote-a")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("treats a missing remote delete as an error", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "missing" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }));

    const client = new HttpGlialClient({
      baseUrl: "http://glial.test",
      fetchImpl: fetchMock,
    });

    await expect(client.deleteRemoteSession("user-a", "missing")).rejects.toThrow(
      "Glial request failed: 404",
    );
  });

  it("loads shared sessions, requests leases, and updates shared values via fetch", async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        session_id: 'shared-a',
        title: 'Shared A',
        snapshot: { session_id: 'shared-a', contexts: {}, taps: {} },
        leases: {},
        last_modified_ms: 1,
      }))
      .mockResolvedValueOnce(jsonResponse({
        tap_id: 'tap-a',
        primary_replica_id: 'headless-a',
        priority: 50,
        granted_ms: 2,
        granted: true,
      }))
      .mockResolvedValueOnce(jsonResponse({
        session_id: 'shared-a',
        title: 'Shared A',
        snapshot: {
          session_id: 'shared-a',
          contexts: {
            'main-home': {
              path: 'main-home',
              name: 'main-home',
              children: [],
              drips: {
                'app:Count': {
                  grip_id: 'app:Count',
                  name: 'Count',
                  value: 7,
                  taps: [],
                },
              },
            },
          },
          taps: {},
        },
        leases: {},
        last_modified_ms: 3,
      }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const client = new HttpGlialClient({
      baseUrl: 'http://glial.test',
      fetchImpl: fetchMock,
    });

    const shared = await client.loadSharedSession('user-a', 'shared-a');
    expect(shared.session_id).toBe('shared-a');

    const lease = await client.requestTapLease('user-a', 'shared-a', 'tap-a', 'headless-a', 50);
    expect(lease.primary_replica_id).toBe('headless-a');

    const updated = await client.updateSharedValue('user-a', 'shared-a', {
      path: 'main-home',
      grip_id: 'app:Count',
      value: 7,
    });
    expect((updated.snapshot.contexts as Record<string, { drips: Record<string, { value: number }> }>)['main-home'].drips['app:Count'].value).toBe(7);

    await expect(client.releaseTapLease('user-a', 'shared-a', 'tap-a', 'headless-a')).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("subscribes to shared session websocket snapshots", async () => {
    FakeWebSocket.instances = [];
    const snapshots: string[] = [];
    const errors: unknown[] = [];
    const client = new HttpGlialClient({
      baseUrl: "http://glial.test",
      fetchImpl: vi.fn<typeof fetch>(),
      webSocketFactory: (url) => new FakeWebSocket(url),
    });

    const subscription = client.subscribeSharedSession(
      "user-a",
      "shared-a",
      {
        onSnapshot: (session) => snapshots.push(session.session_id),
        onError: (error) => errors.push(error),
      },
      "replica-a",
    );

    expect(FakeWebSocket.instances).toHaveLength(1);
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toBe(
      "ws://glial.test/shared-sessions/shared-a/ws?user_id=user-a&replica_id=replica-a",
    );

    socket.emitOpen();
    socket.emitMessage({
      type: "shared_session_snapshot",
      session: {
        session_id: "shared-a",
        snapshot: { contexts: {} },
        leases: {},
        last_modified_ms: 1,
      },
    });
    socket.emitMessage({ type: "error", message: "bad things" });

    expect(snapshots).toEqual(["shared-a"]);
    expect(errors).toHaveLength(1);

    subscription.close();
    expect(socket.closed).toBe(true);
  });
});
