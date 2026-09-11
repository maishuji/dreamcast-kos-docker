"""Compatibility entry point for dcdocker build dc-chain."""

from dcdocker.cli import toolchain_command as main, legacy_notice


if __name__ == "__main__":
    legacy_notice("dc-chain")
    main()  # pylint: disable=no-value-for-parameter
