from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from solo.app import create_app
from solo.project import ensure_project


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    (root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=solo",
            "-c",
            "user.email=solo@example.invalid",
            "commit",
            "-m",
            "init",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.end_headers()
        self.wfile.write(f"proxied {self.path}".encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        return


class EditorProxyTests(unittest.TestCase):
    def test_editor_host_is_proxied_before_normal_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            project = ensure_project(root)
            server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = int(server.server_address[1])
            try:
                editor_id = "editor-test"
                record_path = project.runtime_dir / "editors" / f"{editor_id}.json"
                record_path.write_text(
                    (
                        "{\n"
                        f'  "editorId": "{editor_id}",\n'
                        f'  "localUrl": "http://127.0.0.1:{port}",\n'
                        f'  "pid": {os.getpid()},\n'
                        f'  "port": {port},\n'
                        f'  "scopePath": "{root}"\n'
                        "}\n"
                    ),
                    encoding="utf-8",
                )

                client = TestClient(create_app(root))
                response = client.get(
                    "/static/app.js?x=1",
                    headers={"host": f"{editor_id}.solo.example.com"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.text, "proxied /static/app.js?x=1")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
