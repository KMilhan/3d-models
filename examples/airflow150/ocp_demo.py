from __future__ import annotations

from ocp_vscode import Camera, show

from airflow150.model import build_all_components


def main() -> None:
    """Quick demo: show all airflow150 parts in vscode-ocp-cad-viewer."""
    parts = build_all_components()
    names = list(parts.keys())
    show(*(parts[name] for name in names), names=names, axes=True, reset_camera=Camera.RESET)


if __name__ == "__main__":
    main()
