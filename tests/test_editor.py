from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from solo.editor import code_server_env


class EditorTests(unittest.TestCase):
    def test_code_server_env_removes_ide_and_proxy_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VSCODE_IPC_HOOK_CLI": "/tmp/vscode.sock",
                "https_proxy": "http://127.0.0.1:10809",
                "HTTPS_PROXY": "http://127.0.0.1:10809",
                "SOLO_KEEP": "yes",
            },
            clear=True,
        ):
            env = code_server_env()

        self.assertNotIn("VSCODE_IPC_HOOK_CLI", env)
        self.assertNotIn("https_proxy", env)
        self.assertNotIn("HTTPS_PROXY", env)
        self.assertEqual(env["SOLO_KEEP"], "yes")


if __name__ == "__main__":
    unittest.main()
