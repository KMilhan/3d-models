from __future__ import annotations

from ocp_vscode import Camera, show

from .model import build_component_d_parametric_louver


def main() -> None:
    """Show Component D (Voronoi parametric louver) in OCP CAD Viewer."""
    part = build_component_d_parametric_louver(fillets=True)
    show(part, names=["airflow150_D_parametric_louver"], axes=True, reset_camera=Camera.RESET)


if __name__ == "__main__":
    main()
