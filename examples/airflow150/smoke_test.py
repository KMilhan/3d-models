from __future__ import annotations

from build123d import Box, BuildPart
from ocp_vscode import Camera, show


def main() -> None:
    """Smoke test: show a simple box to verify OCP CAD Viewer connection."""
    with BuildPart() as part:
        Box(50, 30, 20)

    show(part.part, names=["smoke_box"], axes=True, reset_camera=Camera.RESET)
    print("OK - OCP CAD Viewer is connected.")


if __name__ == "__main__":
    main()
