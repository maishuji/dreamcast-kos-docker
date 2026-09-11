"""Compatibility entry point for dcdocker build kos-image."""

from dcdocker.cli import full_image_command as main, legacy_notice


if __name__ == "__main__":
    legacy_notice("kos-image")
    main()  # pylint: disable=no-value-for-parameter
