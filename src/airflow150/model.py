from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Locations,
    Mode,
    Part,
    Plane,
    PolarLocations,
    Rectangle,
    add,
    chamfer,
    export_brep,
    export_step,
    export_stl,
    extrude,
    fillet,
    loft,
)
from build123d import Polygon as BPolygon

from .louver import build_component_d_parametric_louver

ExportFormat = Literal["step", "stl", "brep"]
SUPPORTED_EXPORT_FORMATS: tuple[ExportFormat, ...] = ("step", "stl", "brep")
DEFAULT_OUT_DIR = Path.cwd() / "models" / "out" / "airflow150"


# Shared airflow dimensions
FLOW_DIAMETER = 150.0
FLOW_RADIUS = FLOW_DIAMETER / 2.0
FLOW_AREA = math.pi * FLOW_RADIUS * FLOW_RADIUS


def log_blend(value: float, gain: float) -> float:
    """Blend 0..1 using a logarithmic curve for smoother bellmouth growth."""
    return math.log1p(gain * value) / math.log1p(gain)


def build_component_a_wall_anchor_sleeve() -> Part:
    """Component A: wall-anchor sleeve with O-ring grooves and female bayonet cuts."""
    sleeve_id = 150.0
    sleeve_od = 154.0
    sleeve_length = 50.0

    flange_radial = 10.0
    flange_thickness = 4.0

    groove_width = 2.0
    groove_depth = 1.5
    groove_centers = (13.0, 23.0, 33.0)

    bayonet_count = 3
    bayonet_radial_depth = 1.8
    bayonet_entry_depth = 3.6
    bayonet_lock_depth = 1.8
    bayonet_turn_angle = 22.0
    bayonet_slot_angle = 16.0
    bayonet_floor_z = 0.6

    outer_radius = sleeve_od / 2.0
    inner_radius = sleeve_id / 2.0

    with BuildPart() as sleeve:
        Cylinder(
            outer_radius,
            sleeve_length,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        Cylinder(
            inner_radius,
            sleeve_length + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )

        # Anti over-insertion flange at the insertion face.
        Cylinder(
            outer_radius + flange_radial,
            flange_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        # Shared annular groove cutter for the three O-ring grooves.
        with BuildPart() as groove_cutter:
            Cylinder(
                outer_radius + 0.2,
                groove_width,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
            Cylinder(
                outer_radius - groove_depth,
                groove_width + 0.2,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        for groove_center in groove_centers:
            z0 = groove_center - groove_width / 2.0
            add(groove_cutter.part.moved(Location((0, 0, z0))), mode=Mode.SUBTRACT)

        # Female bayonet pockets (L-shape: entry + twist lock pocket).
        tangential_width = math.radians(bayonet_slot_angle) * inner_radius
        for index in range(bayonet_count):
            base_angle = index * 360.0 / bayonet_count

            entry_pocket = Box(
                bayonet_radial_depth,
                tangential_width,
                bayonet_entry_depth,
                align=(Align.MIN, Align.CENTER, Align.MIN),
            )
            entry_pocket = entry_pocket.moved(
                Location((inner_radius - bayonet_radial_depth + 0.2, 0, bayonet_floor_z))
            ).rotate(Axis.Z, base_angle)
            add(entry_pocket, mode=Mode.SUBTRACT)

            lock_pocket = Box(
                bayonet_radial_depth + 0.2,
                tangential_width + 2.0,
                bayonet_lock_depth + 0.4,
                align=(Align.MIN, Align.CENTER, Align.MIN),
            )
            lock_pocket = lock_pocket.moved(
                Location(
                    (
                        inner_radius - bayonet_radial_depth + 0.1,
                        0,
                        bayonet_floor_z + bayonet_entry_depth - bayonet_lock_depth,
                    )
                )
            ).rotate(Axis.Z, base_angle + bayonet_turn_angle)
            add(lock_pocket, mode=Mode.SUBTRACT)

    return sleeve.part


def build_component_b_selector_chamber() -> Part:
    """Component B: 3-way selector chamber with dual gate slots and anti-leak lips."""
    wall_thickness = 3.2
    main_length = 175.0
    branch_length = 120.0
    branch_x = 92.0

    outer_diameter = FLOW_DIAMETER + 2.0 * wall_thickness
    outer_radius = outer_diameter / 2.0

    slot_width = 4.0
    slot_x_positions = (main_length - 26.0, branch_x + 6.0)
    slot_span_y = outer_diameter + 10.0
    slot_span_z = branch_length + 25.0

    slot_lip_thickness = 1.0
    slot_lip_height = 16.0
    slot_lip_z0 = -2.0

    # Male bayonet lugs to mate with Component A female pockets.
    lug_count = 3
    lug_radius = FLOW_RADIUS + 0.2
    lug_radial = 1.6
    lug_tangential = math.radians(15.0) * lug_radius
    lug_axial = 3.0
    lug_x = -2.8

    with BuildPart() as chamber:
        # Outer manifold shell (main run + side/top branch).
        Cylinder(
            outer_radius,
            main_length,
            rotation=(0, 90, 0),
            align=(Align.MIN, Align.CENTER, Align.CENTER),
        )
        with Locations((branch_x, 0, 0)):
            Cylinder(outer_radius, branch_length)

        # Cap the lower branch side so the chamber stays 3-way.
        with Locations((branch_x, 0, -branch_length / 2.0)):
            Cylinder(
                outer_radius,
                wall_thickness + 0.2,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
            )

        # Constant-area internal paths (diameter 150 mm).
        Cylinder(
            FLOW_RADIUS,
            main_length + 0.2,
            rotation=(0, 90, 0),
            align=(Align.MIN, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )
        with Locations((branch_x, 0, 0)):
            Cylinder(FLOW_RADIUS, branch_length + 0.2, mode=Mode.SUBTRACT)

        # Two parallel vertical slots for the sliding gate logic.
        for slot_x in slot_x_positions:
            with Locations((slot_x, 0, 0)):
                Box(
                    slot_width,
                    slot_span_y,
                    slot_span_z,
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.SUBTRACT,
                )

        # 1 mm anti-bypass lips around each slot entrance.
        for slot_x in slot_x_positions:
            with Locations((slot_x, outer_radius - slot_lip_thickness / 2.0, slot_lip_z0)):
                Box(
                    slot_width + 2.0 * slot_lip_thickness,
                    slot_lip_thickness,
                    slot_lip_height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )
            with Locations((slot_x, -outer_radius + slot_lip_thickness / 2.0, slot_lip_z0)):
                Box(
                    slot_width + 2.0 * slot_lip_thickness,
                    slot_lip_thickness,
                    slot_lip_height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )

        # Three twist-lock lugs on the inlet side.
        for index in range(lug_count):
            angle_deg = index * 360.0 / lug_count
            angle_rad = math.radians(angle_deg)
            lug = Box(
                lug_axial,
                lug_tangential,
                lug_radial,
                align=(Align.MIN, Align.CENTER, Align.MIN),
            )
            lug = lug.rotate(Axis.X, angle_deg).moved(
                Location(
                    (lug_x, lug_radius * math.cos(angle_rad), lug_radius * math.sin(angle_rad))
                )
            )
            add(lug)

    return chamber.part


def build_component_b_shutter_plate() -> Part:
    """Component B shutter: rigid 3.5 mm plate with chamfer and ergonomic handle."""
    plate_thickness = 3.5
    plate_span_y = 170.0
    plate_span_z = 130.0
    plate_edge_chamfer = 0.5

    handle_small_radius = 8.0
    handle_large_radius = 11.0
    handle_offset_x = 14.0
    handle_z = plate_span_z / 2.0 + 10.0

    with BuildPart() as shutter:
        Box(plate_thickness, plate_span_y, plate_span_z)
        chamfer(shutter.edges(), plate_edge_chamfer)

        with Locations((0, 0, handle_z)):
            Cylinder(
                handle_small_radius,
                plate_thickness + 2.0,
                rotation=(0, 90, 0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            )
        with Locations((handle_offset_x, 0, handle_z)):
            Cylinder(
                handle_large_radius,
                plate_thickness + 2.0,
                rotation=(0, 90, 0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            )
        with Locations((handle_offset_x / 2.0, 0, handle_z)):
            Box(
                handle_offset_x,
                handle_large_radius * 1.2,
                plate_thickness + 2.0,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            )

        handle_edges = [edge for edge in shutter.edges() if edge.center().Z > plate_span_z / 2.0]
        if handle_edges:
            try:
                fillet(handle_edges, 2.0)
            except Exception:
                try:
                    fillet(handle_edges, 0.5)
                except Exception:
                    pass

    return shutter.part


def square_radius(side: float, angle_rad: float) -> float:
    """Radius from center to square perimeter at a given angle."""
    denom = max(abs(math.cos(angle_rad)), abs(math.sin(angle_rad)), 1e-9)
    return (side / 2.0) / denom


def blended_profile_points(
    square_side: float,
    circle_diameter: float,
    blend: float,
    point_count: int,
) -> list[tuple[float, float]]:
    """Blend square and circle profiles for loft section generation."""
    points: list[tuple[float, float]] = []
    circle_radius = circle_diameter / 2.0

    for idx in range(point_count):
        angle = 2.0 * math.pi * idx / point_count
        square_r = square_radius(square_side, angle)
        radius = square_r + (circle_radius - square_r) * blend
        points.append((radius * math.cos(angle), radius * math.sin(angle)))

    return points


def build_component_c_bellmouth_adapter() -> Part:
    """Component C: 100 mm square to 150 mm circular logarithmic bellmouth adapter."""
    base_xy = 120.0
    base_thickness = 5.0

    mount_hole_diameter = 3.5
    mount_pitch = 100.0

    square_inlet = 100.0
    circular_outlet = 150.0
    loft_height = 60.0
    wall_thickness = 3.0

    loft_gain = 4.6
    loft_steps = 28
    profile_points = 96

    flange_diameter = 184.0
    flange_height = 8.0

    magnet_count = 8
    magnet_pcd = 170.0
    magnet_hole_diameter = 5.2
    magnet_hole_depth = 5.5
    magnet_air_gap = 0.1

    z0 = base_thickness
    z1 = base_thickness + loft_height

    with BuildPart() as adapter:
        # Base plate.
        Box(
            base_xy,
            base_xy,
            base_thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        # Outer logarithmic loft shell.
        outer_sections = []
        for step in range(loft_steps + 1):
            u = step / loft_steps
            blend = log_blend(u, loft_gain)
            z = z0 + u * loft_height
            points = blended_profile_points(
                square_inlet + 2.0 * wall_thickness,
                circular_outlet + 2.0 * wall_thickness,
                blend,
                profile_points,
            )
            with BuildSketch(Plane.XY.offset(z)) as section:
                BPolygon(*points)
            outer_sections.append(section.sketch)

        loft(sections=outer_sections)

        # 150 mm-side magnet flange.
        with Locations((0, 0, z1)):
            Cylinder(
                flange_diameter / 2.0,
                flange_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
            Cylinder(
                circular_outlet / 2.0,
                flange_height + 0.2,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # Inner logarithmic bellmouth subtraction.
        inner_sections = []
        for step in range(loft_steps + 1):
            u = step / loft_steps
            blend = log_blend(u, loft_gain)
            z = z0 + u * loft_height
            points = blended_profile_points(
                square_inlet,
                circular_outlet,
                blend,
                profile_points,
            )
            with BuildSketch(Plane.XY.offset(z)) as section:
                BPolygon(*points)
            inner_sections.append(section.sketch)

        loft(sections=inner_sections, mode=Mode.SUBTRACT)

        # Open square inlet through base plate.
        with BuildSketch(Plane.XY.offset(-0.1)) as inlet:
            Rectangle(square_inlet, square_inlet)
        extrude(inlet.sketch, amount=base_thickness + 0.2, mode=Mode.SUBTRACT)

        # Four M3 mounting holes at 100 x 100 pitch.
        for sx in (-0.5, 0.5):
            for sy in (-0.5, 0.5):
                with Locations((sx * mount_pitch, sy * mount_pitch, -0.1)):
                    Cylinder(
                        mount_hole_diameter / 2.0,
                        base_thickness + 0.2,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )

        # Eight blind magnet pockets on 170 mm PCD with 0.1 mm insertion air gap.
        with PolarLocations(magnet_pcd / 2.0, magnet_count):
            with Locations((0, 0, z1 + flange_height - magnet_hole_depth)):
                Cylinder(
                    (magnet_hole_diameter + magnet_air_gap) / 2.0,
                    magnet_hole_depth,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    return adapter.part




COMPONENT_BUILDERS: dict[str, Callable[[], Part]] = {
    "airflow150_A_wall_anchor_sleeve": build_component_a_wall_anchor_sleeve,
    "airflow150_B_selector_chamber": build_component_b_selector_chamber,
    "airflow150_B_shutter_plate": build_component_b_shutter_plate,
    "airflow150_C_bellmouth_adapter": build_component_c_bellmouth_adapter,
    "airflow150_D_parametric_louver": build_component_d_parametric_louver,
}


def available_component_names() -> tuple[str, ...]:
    """Return all valid component names in stable export order."""
    return tuple(COMPONENT_BUILDERS.keys())


def build_components(names: Sequence[str] | None = None) -> dict[str, Part]:
    """Build selected components only (or all when names is None)."""
    target_names = available_component_names() if names is None else tuple(names)
    built: dict[str, Part] = {}
    for name in target_names:
        builder = COMPONENT_BUILDERS.get(name)
        if builder is None:
            raise KeyError(name)
        built[name] = builder()
    return built


def export_part_files(
    part: Part,
    stem: str,
    out_dir: Path,
    formats: Sequence[ExportFormat] = SUPPORTED_EXPORT_FORMATS,
) -> list[Path]:
    """Export one part in the requested CAD formats."""
    out_dir.mkdir(parents=True, exist_ok=True)

    exported_paths: list[Path] = []
    for file_format in formats:
        if file_format == "step":
            path = out_dir / f"{stem}.step"
            export_step(part, path)
            exported_paths.append(path)
        elif file_format == "stl":
            path = out_dir / f"{stem}.stl"
            export_stl(part, path)
            exported_paths.append(path)
        elif file_format == "brep":
            path = out_dir / f"{stem}.brep"
            export_brep(part, path)
            exported_paths.append(path)

    return exported_paths


def build_all_components() -> dict[str, Part]:
    """Build every modular airflow diversion component."""
    return build_components()


def export_components(
    out_dir: Path = DEFAULT_OUT_DIR,
    formats: Sequence[ExportFormat] = SUPPORTED_EXPORT_FORMATS,
    names: Sequence[str] | None = None,
) -> dict[str, list[Path]]:
    """Build all components and export each part to the requested formats."""
    components = build_components(names=names)
    exported: dict[str, list[Path]] = {}
    for name, part in components.items():
        exported[name] = export_part_files(part, name, out_dir=out_dir, formats=formats)
    return exported


def main() -> None:
    """Build and export all parts to STEP/STL/BREP under models/out."""
    print(f"Target airflow area: {FLOW_AREA:.1f} mm^2")

    exported = export_components(out_dir=DEFAULT_OUT_DIR, formats=SUPPORTED_EXPORT_FORMATS)
    for name, paths in exported.items():
        joined = ", ".join(path.suffix for path in paths)
        print(f"Exported {name}: {joined}")


if __name__ == "__main__":
    main()
