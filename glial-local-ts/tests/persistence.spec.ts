import { describe, expect, it } from "vitest";
import {
  InMemoryGripSessionPersistence,
  type PersistedChange,
  type SessionSnapshot,
} from "../src";

function makeContextSnapshot(sessionId: string): SessionSnapshot {
  return {
    session_id: sessionId,
    contexts: {
      "/root": {
        path: "/root",
        name: "root",
        children: [],
        drips: {},
      },
    },
  };
}

describe("InMemoryGripSessionPersistence", () => {
  it("creates, lists, hydrates, writes changes, collapses, and removes sessions", async () => {
    const persistence = new InMemoryGripSessionPersistence();
    const summary = await persistence.newSession({
      session_id: "session-a",
      title: "A",
      initial_snapshot: makeContextSnapshot("session-a"),
    });
    expect(summary.session_id).toBe("session-a");

    const listed = await persistence.listSessions();
    expect(listed.map((entry) => entry.session_id)).toContain("session-a");

    const change: PersistedChange = {
      change_id: "change-1",
      session_id: "session-a",
      source: "local",
      status: "applied",
      origin_mutation_seq: 1,
      target_kind: "drip",
      path: "/root",
      grip_id: "app:value",
      payload: {
        grip_id: "app:value",
        name: "value",
        value: 42,
        taps: [],
      },
    };
    await persistence.writeIncrementalChange("session-a", change);

    let hydrated = await persistence.hydrate("session-a");
    expect(hydrated.snapshot.contexts["/root"]?.drips["app:value"]?.value).toBe(42);
    expect(hydrated.applied_changes).toHaveLength(1);

    await persistence.collapse("session-a");
    hydrated = await persistence.hydrate("session-a");
    expect(hydrated.applied_changes).toHaveLength(0);
    expect(hydrated.snapshot.contexts["/root"]?.drips["app:value"]?.value).toBe(42);

    await persistence.removeSession({ session_id: "session-a", scope: "local_only" });
    expect(await persistence.getSession("session-a")).toBeNull();
  });

  it("emits delta and sharing state events", async () => {
    const persistence = new InMemoryGripSessionPersistence();
    await persistence.newSession({ session_id: "session-b" });
    const events: string[] = [];
    const unsubscribe = await persistence.subscribe("session-b", (event) => {
      events.push(event.kind);
    });

    await persistence.writeIncrementalChange("session-b", {
      change_id: "change-2",
      session_id: "session-b",
      source: "local",
      status: "pending_sync",
      origin_mutation_seq: 2,
      target_kind: "context",
      path: "/root",
      payload: {
        path: "/root",
        name: "root",
        children: [],
        drips: {},
      },
    });
    await persistence.enableSharing({
      session_id: "session-b",
      mode: "share_local_session",
    });
    unsubscribe();

    expect(events).toContain("delta");
    expect(events).toContain("sharing_state");
  });
});
