"""Tests for scripts/deploy_web.py's pure parts (the AWS calls are checked by hand on deploy)."""

import importlib.util
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy_web.py"
spec = importlib.util.spec_from_file_location("deploy_web", SCRIPT)
deploy_web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy_web)


def exports(source: str) -> dict[str, str]:
    return dict(re.findall(r'export const (\w+) = "([^"]*)";', source))


def test_config_js_has_the_same_exports_as_the_local_one():
    local = exports((deploy_web.WEB / "config.js").read_text())
    deployed = exports(deploy_web.config_js("https://api.example/", "wss://ws.example/prod"))
    assert deployed.keys() == local.keys()
    assert deployed == {"API_URL": "https://api.example", "WS_URL": "wss://ws.example/prod"}


def test_web_files_skip_config_and_include_the_page():
    files = deploy_web.web_files()
    assert "index.html" in files
    assert "js/app.js" in files
    assert "config.js" not in files


def test_web_files_never_include_local_tooling(tmp_path):
    for name in [
        "index.html",
        "js/app.js",
        "config.js",
        "package.json",
        "package-lock.json",
        "node_modules/pkg/index.js",
        ".cache/x",
        "js/.DS_Store",
    ]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")
    assert sorted(deploy_web.web_files(tmp_path)) == ["index.html", "js/app.js"]


def test_content_types():
    assert deploy_web.content_type("js/app.js") == "text/javascript; charset=utf-8"
    assert deploy_web.content_type("index.html") == "text/html; charset=utf-8"
    assert deploy_web.content_type("css/style.css") == "text/css; charset=utf-8"
