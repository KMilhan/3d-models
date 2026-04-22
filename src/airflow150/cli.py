from __future__ import annotations

import argparse
from pathlib import Path

from .model import (
    DEFAULT_OUT_DIR,
    FLOW_AREA,
    SUPPORTED_EXPORT_FORMATS,
    ExportFormat,
    available_component_names,
    export_components,
)

FORMAT_LOOKUP: dict[str, ExportFormat] = {
    "step": "step",
    "stl": "stl",
    "brep": "brep",
}


def parse_formats(raw_formats: list[str]) -> tuple[ExportFormat, ...]:
    """Normalize --format input values into export format literals."""
    if not raw_formats or "all" in raw_formats:
        return SUPPORTED_EXPORT_FORMATS

    normalized: list[ExportFormat] = []
    for raw in raw_formats:
        candidate = FORMAT_LOOKUP.get(raw.lower())
        if candidate and candidate not in normalized:
            normalized.append(candidate)

    return tuple(normalized) if normalized else SUPPORTED_EXPORT_FORMATS


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser for CAD export workflows."""
    parser = argparse.ArgumentParser(description="Export airflow150 CAD components")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="output directory for generated CAD files",
    )
    parser.add_argument(
        "--format",
        dest="formats",
        action="append",
        choices=(*SUPPORTED_EXPORT_FORMATS, "all"),
        default=[],
        help="export format (repeatable). default: all",
    )
    parser.add_argument(
        "--component",
        dest="components",
        action="append",
        help="component key to export selectively (repeatable)",
    )
    return parser


def main() -> None:
    """CLI entry point for exporting modular airflow diverter components."""
    parser = build_parser()
    args = parser.parse_args()

    export_formats = parse_formats(args.formats)
    print(f"Target airflow area: {FLOW_AREA:.1f} mm^2")

    if args.components:
        requested = list(dict.fromkeys(args.components))
        valid_names = available_component_names()

        invalid = [name for name in requested if name not in valid_names]
        if invalid:
            parser.error(
                "unknown component(s): "
                + ", ".join(invalid)
                + "\nvalid components: "
                + ", ".join(valid_names)
            )

        exported = export_components(out_dir=args.out_dir, formats=export_formats, names=requested)
        for name, paths in exported.items():
            joined = ", ".join(path.name for path in paths)
            print(f"Exported {name}: {joined}")
        return

    exported = export_components(out_dir=args.out_dir, formats=export_formats)
    for name, paths in exported.items():
        joined = ", ".join(path.name for path in paths)
        print(f"Exported {name}: {joined}")


if __name__ == "__main__":
    main()
