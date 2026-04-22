from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .model import (
    DEFAULT_OUT_DIR,
    SUPPORTED_EXPORT_FORMATS,
    available_component_names,
    export_components,
)


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser for Antigravity visualization."""
    parser = argparse.ArgumentParser(description="Visualize airflow150 parts in Antigravity")
    parser.add_argument(
        "--component",
        dest="components",
        action="append",
        help="component key to show selectively (repeatable)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="directory for generated CAD files before opening Antigravity",
    )
    parser.add_argument(
        "--format",
        choices=SUPPORTED_EXPORT_FORMATS,
        default="brep",
        help="CAD format to open in Antigravity (default: brep)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print Antigravity command without launching GUI",
    )
    return parser


def main() -> None:
    """Build components, export files, and open them in Antigravity."""
    parser = build_parser()
    args = parser.parse_args()

    valid_names = available_component_names()

    if args.components:
        names = list(dict.fromkeys(args.components))
        invalid = [name for name in names if name not in valid_names]
        if invalid:
            parser.error(
                "unknown component(s): "
                + ", ".join(invalid)
                + "\nvalid components: "
                + ", ".join(valid_names)
            )
    else:
        names = list(valid_names)

    exported = export_components(out_dir=args.out_dir, formats=(args.format,), names=names)
    export_paths = [path for paths in exported.values() for path in paths]

    command = ["antigravity", *[str(path) for path in export_paths]]
    print("Launching:", " ".join(command))
    if args.dry_run:
        return

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as error:
        raise SystemExit("`antigravity` command not found on PATH.") from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"`antigravity` exited with code {error.returncode}.") from error


if __name__ == "__main__":
    main()
