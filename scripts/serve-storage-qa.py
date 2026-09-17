#!/usr/bin/env python3
"""Isolated browser QA: disposable business data, no SSH or Feishu credentials."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="entropycamp-qa-") as temporary:
    root = Path(temporary)
    os.environ.update(CODEX_HOME=str(root / "codex"), LUMEN_WIDGET_DIRECTORY=str(root / "widget"),
                      LUMEN_REMINDER_DATA_DIR=str(root / "feishu"), LUMEN_CODEX_REMOTE_CONFIG=str(root / "no-remotes.json"),
                      ENTROPYCAMP_DATA_DIR=str(root / "state"))
    import run
    from state_store import BusinessStateStore, CARDS

    run.CODEX_BRIDGE = SimpleNamespace(list_threads=lambda **kwargs: [])
    run.REMOTE_CODEX_BRIDGES = {}
    run.BUSINESS_STORE = BusinessStateStore(root / "state")
    run.BUSINESS_STORE.initialize({CARDS: [{"id": "qa-seed", "title": "SQLite seed", "intervalMs": 1800000,
                                         "intervalValue": 30, "intervalUnit": "minute", "started": False, "nextAt": None,
                                         "createdAt": 1, "codexThreadId": ""}]}, "qa")
    server = run.ReminderServer(("127.0.0.1", 8766), run.ReminderHandler)
    print("QA_URL=http://127.0.0.1:8766/?variant=A", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
