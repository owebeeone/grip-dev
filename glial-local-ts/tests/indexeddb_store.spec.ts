import "fake-indexeddb/auto";

import { describe, expect, it } from "vitest";
import {
  bindBrowserSessionToExistingSession,
  createBrowserSessionId,
  ensureBrowserSessionRecord,
  IndexedDbGripSessionStore,
} from "../src";

describe("IndexedDbGripSessionStore", () => {
  it("persists sessions across store instances and supports collapse", async () => {
    const databaseName = `glial-local-test-${Date.now()}`;
    const store = new IndexedDbGripSessionStore({ databaseName });

    await store.newSession({ session_id: "session-a" });
    await store.writeIncrementalChange("session-a", {
      change_id: "change-1",
      session_id: "session-a",
      source: "local",
      status: "applied",
      origin_mutation_seq: 1,
      target_kind: "context",
      path: "/root",
      payload: {
        path: "/root",
        name: "root",
        children: [],
        drips: {},
      },
    });
    await store.writeIncrementalChange("session-a", {
      change_id: "change-2",
      session_id: "session-a",
      source: "local",
      status: "applied",
      origin_mutation_seq: 2,
      target_kind: "drip",
      path: "/root",
      grip_id: "app:value",
      payload: {
        grip_id: "app:value",
        name: "value",
        value: 99,
        taps: [],
      },
    });

    const reloadedStore = new IndexedDbGripSessionStore({ databaseName });
    let hydrated = await reloadedStore.hydrate("session-a");
    expect(hydrated.snapshot.contexts["/root"]?.drips["app:value"]?.value).toBe(99);
    expect(hydrated.applied_changes).toHaveLength(2);

    await reloadedStore.collapse("session-a");
    hydrated = await reloadedStore.hydrate("session-a");
    expect(hydrated.applied_changes).toHaveLength(0);

    await reloadedStore.removeSession({ session_id: "session-a", scope: "local_only" });
    expect(await reloadedStore.getSession("session-a")).toBeNull();
  });

  it("persists browser session records across store instances", async () => {
    const databaseName = `glial-local-browser-test-${Date.now()}`;
    const store = new IndexedDbGripSessionStore({ databaseName });
    const browserSessionId = createBrowserSessionId("indexeddb");

    const initial = await ensureBrowserSessionRecord(store, browserSessionId, {
      title: "Initial browser session",
      storageMode: "local",
    });
    const secondSession = await store.newSession({ title: "Second session" });
    await bindBrowserSessionToExistingSession(store, browserSessionId, secondSession, "local");

    const reloadedStore = new IndexedDbGripSessionStore({ databaseName });
    const listed = await reloadedStore.listBrowserSessions();
    expect(listed).toHaveLength(1);
    expect(listed[0]?.browser_session_id).toBe(browserSessionId);
    expect(listed[0]?.glial_session_id).toBe(secondSession.session_id);
    expect(listed[0]?.glial_session_id).not.toBe(initial.glial_session_id);
  });
});
