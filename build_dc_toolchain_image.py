"""Compatibility entry point for the Dreamcast toolchain builder."""

from dcdocker.cli import toolchain_command as main


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
