"""Compatibility entry point using the ready-image context beside this script."""

from pathlib import Path

from dcdocker.cli import full_image_command

main = full_image_command(Path(__file__).resolve().parent / "kos-ready")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
