from __future__ import annotations

import argparse
import importlib.util
import contextlib
import io
import tempfile
import unittest
from pathlib import Path


def load_installer_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "install_dependencies.py"
    spec = importlib.util.spec_from_file_location("install_dependencies", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallDependenciesTests(unittest.TestCase):
    def test_cloudflared_config_contains_solo_and_wildcard_hosts(self) -> None:
        module = load_installer_module()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            credentials_path = Path(tmp) / "solo.json"
            args = argparse.Namespace(
                cloudflared_hostname="solo.example.com",
                cloudflared_tunnel="solo",
                cloudflared_credentials_file=str(credentials_path),
                cloudflared_config=str(config_path),
                force_cloudflared_config=False,
                solo_port=8765,
            )

            with contextlib.redirect_stdout(io.StringIO()):
                module.write_cloudflared_config(args)

            content = config_path.read_text(encoding="utf-8")
            self.assertIn("tunnel: solo", content)
            self.assertIn("credentials-file: " + str(credentials_path), content)
            self.assertIn("hostname: solo.example.com", content)
            self.assertIn('hostname: "*.solo.example.com"', content)
            self.assertIn("service: http://127.0.0.1:8765", content)
            self.assertIn("service: http_status:404", content)


if __name__ == "__main__":
    unittest.main()
