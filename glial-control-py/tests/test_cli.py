from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from glial_control.cli import run_cli
from glial_net import HttpGlialClient
from glial_router import create_app


def _seed_shared_session(client: HttpGlialClient, session_id: str = "shared-a") -> None:
    client.save_remote_session(
        "demo-user",
        session_id,
        {
            "session_id": session_id,
            "contexts": {
                "main-home": {
                    "path": "main-home",
                    "name": "main-home",
                    "children": [],
                    "drips": {
                        "app:Count": {
                            "grip_id": "app:Count",
                            "name": "Count",
                            "value": 3,
                            "taps": [],
                        }
                    },
                }
            },
        },
        title="Shared A",
    )
    client.save_shared_session(
        "demo-user",
        session_id,
        {
            "session_id": session_id,
            "contexts": {
                "main-home": {
                    "path": "main-home",
                    "name": "main-home",
                    "children": [],
                    "drips": {
                        "app:Count": {
                            "grip_id": "app:Count",
                            "name": "Count",
                            "value": 3,
                            "taps": [
                                {
                                    "tap_id": "tap-count",
                                    "tap_type": "AtomValueTap",
                                    "mode": "replicated",
                                    "role": "primary",
                                    "provides": ["app:Count"],
                                }
                            ],
                        }
                    },
                }
            },
            "taps": {
                "tap-count": {
                    "tap_id": "tap-count",
                    "tap_type": "AtomValueTap",
                    "home_path": "main-home",
                    "mode": "replicated",
                    "role": "primary",
                    "provides": ["app:Count"],
                }
            },
        },
        title="Shared A",
    )


def test_cli_lists_sessions_and_taps_and_updates_values() -> None:
    test_client = TestClient(create_app())
    api = HttpGlialClient(client=test_client)
    _seed_shared_session(api)

    out = io.StringIO()
    assert run_cli(["list-sessions"], stdout=out, client=api) == 0
    sessions = json.loads(out.getvalue())
    assert sessions[0]["session_id"] == "shared-a"

    out = io.StringIO()
    assert run_cli(["list-taps", "shared-a"], stdout=out, client=api) == 0
    taps = json.loads(out.getvalue())
    assert "tap-count" in taps

    out = io.StringIO()
    assert (
        run_cli(
            ["request-primary", "shared-a", "tap-count", "--replica-id", "headless-a", "--priority", "50"],
            stdout=out,
            client=api,
        )
        == 0
    )
    lease = json.loads(out.getvalue())
    assert lease["tap_id"] == "tap-count"
    assert lease["primary_replica_id"] == "headless-a"

    out = io.StringIO()
    assert (
        run_cli(
            ["set-value", "shared-a", "main-home", "app:Count", "9"],
            stdout=out,
            client=api,
        )
        == 0
    )
    updated = json.loads(out.getvalue())
    assert updated["snapshot"]["contexts"]["main-home"]["drips"]["app:Count"]["value"] == 9
