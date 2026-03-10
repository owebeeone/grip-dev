import { describe, expect, it, vi } from "vitest";
import { HttpGlialClient, HttpGripSessionLink } from "../src";
import type { PersistedChange } from "../../glial-local-ts/src/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
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
});
