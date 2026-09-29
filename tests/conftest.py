from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from speckit_delivery.core import make_plan
from speckit_delivery.storage import write


class FakeGitHub:
    """Test-only authority; deliberately never exposed through the CLI."""

    def baseline_approval(self, number, path, checksum):
        return {
            "review_id": 1,
            "reviewer": "human",
            "commit": "1" * 40,
            "submitted_at": "2026-01-01T00:00:00Z",
        }

    def final_approval(self, number, head, evidence_hash):
        return {"review_id": 2, "reviewer": "human", "commit": head, "evidence_hash": evidence_hash}


@pytest.fixture
def authority():
    return FakeGitHub()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True)
    # Disposable test repositories contain no real publication or credentials.
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    feature = root / "specs/001-example"
    feature.mkdir(parents=True)
    (root / ".gitignore").write_text(
        "specs/*/delivery/runs/\nspecs/*/delivery/presentations/\nspecs/*/delivery/verification.json\n"
    )
    (feature / "spec.md").write_text("# Example\nFR-001: Greet users.\nAC-001: Prints hello.\n")
    (feature / "plan.md").write_text("Use a small CLI.\n")
    (feature / "tasks.md").write_text("- [ ] T001 Implement greeting\n")
    (root / "greet.py").write_text("print('hello')\n")
    mapping = {
        "title": "Greeting delivery",
        "obligations": [
            {"id": "FR-001", "kind": "requirement", "text": "Greet users", "source": "spec.md"},
            {"id": "AC-001", "kind": "acceptance", "text": "Prints hello", "source": "spec.md"},
            {"id": "T001", "kind": "task", "text": "Implement greeting", "source": "tasks.md"},
        ],
        "scenarios": [
            {
                "id": "greet",
                "title": "Greeting",
                "kind": "cli",
                "obligations": ["FR-001", "AC-001", "T001"],
                "expected": "Print hello and exit zero",
                "command": [sys.executable, "greet.py"],
                "regression": True,
                "assertions": [
                    {"field": "exit_code", "value": 0},
                    {"field": "stdout", "operator": "contains", "value": "hello"},
                ],
            }
        ],
    }
    write(root / "mapping.json", mapping)
    make_plan(root, feature, root / "mapping.json")
    return root, feature


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            if self.path == "/api":
                self.send_header("Content-Type", "application/json")
                body = json.dumps({"message": "hello", "count": 1}).encode()
            else:
                self.send_header("Content-Type", "text/html")
                body = b"<h1>Hello</h1><button onclick=\"this.textContent='Saved'\">Save</button>"
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join()
    httpd.server_close()
