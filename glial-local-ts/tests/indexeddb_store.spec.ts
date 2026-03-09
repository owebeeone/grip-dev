import "fake-indexeddb/auto";

import { describe, expect, it } from "vitest";
import { IndexedDbGripSessionStore } from "../src";

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
});
