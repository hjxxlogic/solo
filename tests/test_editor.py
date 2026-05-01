from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from solo.editor import code_server_env, editor_id_for, editor_id_from_host, editor_public_url


class EditorTests(unittest.TestCase):
    def test_code_server_env_removes_ide_and_proxy_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CODE_SERVER_PARENT_PID": "123",
                "CODE_SERVER_SESSION_SOCKET": "/tmp/code-server.sock",
                "ELECTRON_RUN_AS_NODE": "1",
                "VSCODE_CWD": "/home/hj/work/solo",
                "VSCODE_IPC_HOOK_CLI": "/tmp/vscode.sock",
                "VSCODE_NLS_CONFIG": "{}",
                "https_proxy": "http://127.0.0.1:10809",
                "HTTPS_PROXY": "http://127.0.0.1:10809",
                "PATH": "/usr/bin:/home/hj/.vscode-server/bin/abc/bin/remote-cli:/home/hj/node/bin",
                "SOLO_KEEP": "yes",
            },
            clear=True,
        ):
            env = code_server_env()

        self.assertNotIn("CODE_SERVER_PARENT_PID", env)
        self.assertNotIn("CODE_SERVER_SESSION_SOCKET", env)
        self.assertNotIn("ELECTRON_RUN_AS_NODE", env)
        self.assertNotIn("VSCODE_CWD", env)
        self.assertNotIn("VSCODE_IPC_HOOK_CLI", env)
        self.assertNotIn("VSCODE_NLS_CONFIG", env)
        self.assertNotIn("https_proxy", env)
        self.assertNotIn("HTTPS_PROXY", env)
        self.assertEqual(env["PATH"], "/usr/bin:/home/hj/node/bin")
        self.assertEqual(env["SOLO_KEEP"], "yes")

    def test_editor_public_url_is_local_for_loopback_origin(self) -> None:
        record = {
            "editorId": "editor-1234567890abcdef",
            "port": 41967,
            "localUrl": "http://127.0.0.1:41967",
        }

        self.assertEqual(
            editor_public_url(record, "http://127.0.0.1:8765"),
            "http://127.0.0.1:41967",
        )
        self.assertEqual(
            editor_public_url(record, "http://localhost:8765"),
            "http://127.0.0.1:41967",
        )

    def test_editor_public_url_uses_editor_subdomain_for_remote_origin(self) -> None:
        record = {
            "editorId": "editor-1234567890abcdef",
            "port": 41967,
            "localUrl": "http://127.0.0.1:41967",
        }

        self.assertEqual(
            editor_public_url(record, "https://solo.example.com"),
            "https://editor-1234567890abcdef.solo.example.com",
        )

    def test_editor_id_is_dns_safe_and_decodable_from_host(self) -> None:
        editor_id = editor_id_for(Path("/home/hj/work/solo"))

        self.assertRegex(editor_id, r"^editor-[0-9a-f]{16}$")
        self.assertEqual(editor_id_from_host(f"{editor_id}.solo.example.com"), editor_id)
        self.assertIsNone(editor_id_from_host("solo.example.com"))


if __name__ == "__main__":
    unittest.main()
