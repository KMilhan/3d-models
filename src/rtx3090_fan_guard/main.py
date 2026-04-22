"""
Palit RTX 3090 parametric fan guard.

This script generates a fan guard for the Palit RTX 3090 (GameRock/GamingPro)
using an exact honeycomb guard by default and a fast preview mode on demand.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Iterable
from pathlib import Path

from build123d import (
    BuildPart,
    BuildSketch,
    Circle,
    Location,
    Locations,
    Part,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    add,
    export_brep,
    export_step,
    export_stl,
    extrude,
    fillet,
)

# ==========================================
# PARAMETERS
# ==========================================
WIDTH = 304.0
HEIGHT = 136.0
THICKNESS = 2.4
BORDER_WIDTH = 6.0
HOLE_DIA = 1.8
WALL_THICKNESS = 1.0
CORNER_RADIUS = 10.0
MOUNT_HOLE_DIA = 3.2
FAST_APERTURE = 1.8
P1S_BED_SIZE = 256.0
DEFAULT_SPLIT_MODE = "auto"

OUTPUT_STEM = "rtx3090_fan_guard"
DEFAULT_EXPORT_FORMATS = ("step", "stl", "brep")
DEFAULT_PATTERN_MODE = "exact"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "models" / "out" / "rtx3090_fan_guard"


def phase_start() -> float:
    return time.perf_counter()


def phase_end(phase_seconds: dict[str, float], name: str, start_time: float) -> None:
    phase_seconds[name] = time.perf_counter() - start_time
    print(f"{name}: {phase_seconds[name]:.3f}s")


def requested_export_formats() -> tuple[str, ...]:
    raw_value = os.environ.get("RTX3090_FAN_GUARD_EXPORT_FORMATS")
    if not raw_value:
        return DEFAULT_EXPORT_FORMATS

    formats = tuple(
        item.strip().lower() for item in raw_value.split(",") if item.strip()
    )
    return tuple(fmt for fmt in formats if fmt in DEFAULT_EXPORT_FORMATS)


def requested_pattern_mode() -> str:
    raw_value = os.environ.get("RTX3090_FAN_GUARD_PATTERN", DEFAULT_PATTERN_MODE)
    pattern_mode = raw_value.strip().lower()
    if pattern_mode in {"exact", "fast"}:
        return pattern_mode
    return DEFAULT_PATTERN_MODE


def requested_split_mode() -> str:
    raw_value = os.environ.get("RTX3090_FAN_GUARD_SPLIT", DEFAULT_SPLIT_MODE)
    split_mode = raw_value.strip().lower()
    if split_mode in {"auto", "full", "halves"}:
        return split_mode
    return DEFAULT_SPLIT_MODE


def build_mount_points() -> list[tuple[float, float]]:
    x_offset = WIDTH / 2 - BORDER_WIDTH / 2
    y_offset = HEIGHT / 2 - BORDER_WIDTH / 2
    return [
        (x_offset, y_offset),
        (-x_offset, y_offset),
        (x_offset, -y_offset),
        (-x_offset, -y_offset),
        (0, y_offset),
        (0, -y_offset),
        (x_offset, 0),
        (-x_offset, 0),
    ]


def print_phase_summary(counts: dict[str, int]) -> None:
    for count_name, value in counts.items():
        print(f"{count_name}: {value}")


def point_in_rounded_rectangle(
    x: float,
    y: float,
    width: float,
    height: float,
    corner_radius: float,
) -> bool:
    half_width = width / 2
    half_height = height / 2

    if abs(x) > half_width or abs(y) > half_height:
        return False

    inner_half_width = max(half_width - corner_radius, 0.0)
    inner_half_height = max(half_height - corner_radius, 0.0)

    if abs(x) <= inner_half_width or abs(y) <= inner_half_height:
        return True

    dx = abs(x) - inner_half_width
    dy = abs(y) - inner_half_height
    return dx * dx + dy * dy <= corner_radius * corner_radius


def iter_hex_centers(
    x_count: int,
    y_count: int,
    x_step: float,
    y_step: float,
) -> Iterable[tuple[float, float]]:
    y_origin = -((y_count - 1) * y_step) / 2
    x_origin = -((x_count - 1) * x_step) / 2

    for row_index in range(y_count):
        y_value = y_origin + row_index * y_step
        row_offset = x_step / 2 if row_index % 2 else 0.0
        for column_index in range(x_count):
            x_value = x_origin + column_index * x_step + row_offset
            yield (x_value, y_value)


def build_hole_points(
    x_count: int,
    y_count: int,
    x_step: float,
    y_step: float,
    hole_apothem: float,
    inner_width: float,
    inner_height: float,
    inner_corner_radius: float,
) -> list[tuple[float, float]]:
    hole_circumradius = hole_apothem / math.cos(math.pi / 6)
    safe_width = inner_width - hole_circumradius * 2
    safe_height = inner_height - hole_circumradius * 2
    safe_corner_radius = max(inner_corner_radius - hole_circumradius, 0.0)

    return [
        center
        for center in iter_hex_centers(x_count, y_count, x_step, y_step)
        if point_in_rounded_rectangle(
            x=center[0],
            y=center[1],
            width=safe_width,
            height=safe_height,
            corner_radius=safe_corner_radius,
        )
    ]


def build_strip_locations(
    angle_degrees: float,
    spacing: float,
    span: float,
) -> list[Location]:
    strip_count = math.ceil(span / spacing) + 4
    start_offset = -((strip_count - 1) * spacing) / 2
    normal_angle = math.radians(angle_degrees + 90)

    return [
        Location(
            (
                math.cos(normal_angle) * (start_offset + index * spacing),
                math.sin(normal_angle) * (start_offset + index * spacing),
                0,
            ),
            (0, 0, angle_degrees),
        )
        for index in range(strip_count)
    ]


def export_model(parts: dict[str, Part], out_dir: Path, phase_seconds: dict[str, float]) -> None:
    export_formats = requested_export_formats()
    if not export_formats:
        print("Skipping export because RTX3090_FAN_GUARD_EXPORT_FORMATS is empty.")
        return

    out_dir.mkdir(exist_ok=True)
    print(f"Exporting {', '.join(fmt.upper() for fmt in export_formats)} files...")

    if "step" in export_formats:
        phase_time = phase_start()
        for stem, part in parts.items():
            export_step(part, str(out_dir / f"{stem}.step"))
        phase_end(phase_seconds, "export_step", phase_time)

    if "stl" in export_formats:
        phase_time = phase_start()
        for stem, part in parts.items():
            export_stl(part, str(out_dir / f"{stem}.stl"))
        phase_end(phase_seconds, "export_stl", phase_time)

    if "brep" in export_formats:
        phase_time = phase_start()
        for stem, part in parts.items():
            export_brep(part, str(out_dir / f"{stem}.brep"))
        phase_end(phase_seconds, "export_brep", phase_time)


def build_export_sketches(final_sketch) -> dict[str, object]:
    split_mode = requested_split_mode()
    should_split = split_mode == "halves" or (
        split_mode == "auto" and WIDTH > P1S_BED_SIZE
    )
    if not should_split:
        return {OUTPUT_STEM: final_sketch}

    mask_height = HEIGHT + BORDER_WIDTH * 4
    half_width = WIDTH / 2

    with BuildSketch() as left_mask:
        with Locations((-(WIDTH / 4), 0)):
            Rectangle(half_width, mask_height)

    with BuildSketch() as right_mask:
        with Locations(((WIDTH / 4), 0)):
            Rectangle(half_width, mask_height)

    return {
        f"{OUTPUT_STEM}_left": final_sketch & left_mask.sketch,
        f"{OUTPUT_STEM}_right": final_sketch & right_mask.sketch,
    }


def build_part(sketch, counts: dict[str, int]) -> Part:
    with BuildPart() as fan_guard:
        add(sketch)
        extrude(amount=THICKNESS)

        outer_edges = fan_guard.edges().filter_by(lambda edge: edge.length > 20)
        counts["fillet_edges"] = len(outer_edges)
        fillet_radius = 0.6
        try:
            fillet(outer_edges, radius=fillet_radius)
        except ValueError:
            fillet_radius = 0.3
            print("0.6 mm fillet failed, retrying at 0.3 mm.")
            try:
                fillet(outer_edges, radius=fillet_radius)
            except ValueError:
                fillet_radius = 0.0
                print("Fillet skipped because the selected edges are not fillet-safe.")
        counts["fillet_radius_x10"] = int(fillet_radius * 10)

    return fan_guard.part


def main() -> None:
    total_start = phase_start()
    print(f"Starting parametric generation: {WIDTH}x{HEIGHT} mm guard...")

    inner_width = WIDTH - BORDER_WIDTH * 2
    inner_height = HEIGHT - BORDER_WIDTH * 2
    inner_corner_radius = CORNER_RADIUS - BORDER_WIDTH

    spacing = HOLE_DIA + WALL_THICKNESS
    layout_apothem = spacing / 2
    hole_apothem = HOLE_DIA / 2

    x_step = layout_apothem * math.sqrt(3)
    y_step = 2 * layout_apothem

    # The grid only needs to cover the open inner area. This avoids building
    # hundreds of cells that are guaranteed to be clipped away later.
    x_count = math.ceil(inner_width / x_step) + 3
    y_count = math.ceil(inner_height / y_step) + 3
    candidate_holes = x_count * y_count
    pattern_mode = requested_pattern_mode()
    split_mode = requested_split_mode()

    print(f"Using pattern mode: {pattern_mode}")
    print(f"Using split mode: {split_mode}")

    phase_seconds: dict[str, float] = {}
    counts = {"mount_holes": len(build_mount_points())}

    if pattern_mode == "exact":
        hole_points = build_hole_points(
            x_count=x_count,
            y_count=y_count,
            x_step=x_step,
            y_step=y_step,
            hole_apothem=hole_apothem,
            inner_width=inner_width,
            inner_height=inner_height,
            inner_corner_radius=inner_corner_radius,
        )
        counts["candidate_holes"] = candidate_holes
        counts["valid_holes"] = len(hole_points)
        print(f"Generating honeycomb with {x_count}x{y_count} holes...")
        print(f"Filtered to {len(hole_points)} fully contained holes.")
    else:
        fast_pitch = FAST_APERTURE + WALL_THICKNESS
        slot_span = inner_width + fast_pitch * 2
        slot_locations = build_strip_locations(0.0, fast_pitch, inner_height)
        counts["aperture_x10"] = int(FAST_APERTURE * 10)
        counts["preview_slots"] = len(slot_locations)
        print(
            "Generating fast preview slotted guard with "
            f"{counts['preview_slots']} slots. "
            "Use exact mode for the final 2 mm blocking part."
        )

    phase_time = phase_start()
    with BuildSketch() as outer:
        RectangleRounded(WIDTH, HEIGHT, CORNER_RADIUS)
    phase_end(phase_seconds, "outer_sketch", phase_time)

    phase_time = phase_start()
    with BuildSketch() as inner:
        RectangleRounded(inner_width, inner_height, inner_corner_radius)
    phase_end(phase_seconds, "inner_sketch", phase_time)

    phase_time = phase_start()
    if pattern_mode == "exact":
        with BuildSketch() as pattern:
            with Locations(hole_points):
                RegularPolygon(radius=hole_apothem, side_count=6, major_radius=False)
    else:
        with BuildSketch() as pattern:
            with Locations(slot_locations):
                Rectangle(slot_span, FAST_APERTURE)
    phase_end(phase_seconds, "pattern_sketch", phase_time)

    phase_time = phase_start()
    with BuildSketch() as mounting:
        with Locations(build_mount_points()):
            Circle(radius=MOUNT_HOLE_DIA / 2)
    phase_end(phase_seconds, "mounting_sketch", phase_time)

    phase_time = phase_start()
    if pattern_mode == "exact":
        final_sketch = outer.sketch - pattern.sketch - mounting.sketch
    else:
        valid_slots = inner.sketch & pattern.sketch
        final_sketch = outer.sketch - valid_slots - mounting.sketch
    phase_end(phase_seconds, "final_2d_boolean", phase_time)

    phase_time = phase_start()
    export_sketches = build_export_sketches(final_sketch)
    counts["export_parts"] = len(export_sketches)
    phase_end(phase_seconds, "split_layout", phase_time)

    phase_time = phase_start()
    export_parts = {stem: build_part(sketch, counts) for stem, sketch in export_sketches.items()}
    phase_end(phase_seconds, "extrude", phase_time)

    phase_seconds["fillet"] = phase_seconds["extrude"]
    print(f"fillet: {phase_seconds['fillet']:.3f}s")

    out_dir = DEFAULT_OUT_DIR
    export_model(export_parts, out_dir, phase_seconds)

    phase_end(phase_seconds, "total", total_start)
    print_phase_summary(counts)
    print(f"Successfully saved to {out_dir}")


if __name__ == "__main__":
    main()
