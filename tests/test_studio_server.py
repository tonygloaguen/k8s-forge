from pathlib import Path
from types import ModuleType, SimpleNamespace

import k8s_forge.studio.server as server


def test_run_studio_uses_websockets_backend(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    uvicorn = SimpleNamespace()

    def fake_run(app: object, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    uvicorn.run = fake_run

    def fake_import_module(name: str) -> object:
        assert name == "uvicorn"
        return uvicorn

    routes = ModuleType("k8s_forge.studio.routes")
    routes.create_app = lambda workspace: {"workspace": workspace}

    monkeypatch.setattr(server.importlib, "import_module", fake_import_module)
    monkeypatch.setitem(__import__("sys").modules, "k8s_forge.studio.routes", routes)

    server.run_studio("127.0.0.1", 8765, tmp_path)

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8765
    assert captured["ws"] == "websockets"
    assert captured["app"] == {"workspace": tmp_path}
