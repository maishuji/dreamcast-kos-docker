"""Offline validation for CLI inputs and Docker references."""

import re

import click

# Docker's canonical grammar: https://github.com/distribution/reference/blob/main/regexp.go
TAG = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}"
COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
DOMAIN_PART = r"(?:[A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9-]*[A-Za-z0-9])"
HOST = rf"(?:{DOMAIN_PART}(?:\.{DOMAIN_PART})*|\[[A-Fa-f0-9:]+\])(?::[0-9]+)?"
NAME = rf"(?:{HOST}/)?{COMPONENT}(?:/{COMPONENT})*"
REFERENCE = re.compile(rf"(?P<name>{NAME})(?::(?P<tag>{TAG}))?(?:@(?P<digest>[^@]+))?")


def image_tag(value, option="--image-tag"):
    """Accept one Docker tag, never a full image name."""
    if not re.fullmatch(TAG, value):
        raise click.BadParameter(
            "use 1–128 ASCII letters, digits, underscores, dots or hyphens, "
            "starting with a letter, digit or underscore", param_hint=option,
        )
    return value


def image_reference(value, option="--base-image"):
    """Validate a named reference, supporting tagged images and SHA digests."""
    match = REFERENCE.fullmatch(value)
    if match is None or len(match["name"]) > 255:
        raise click.BadParameter("expected [registry[:port]/]repository[:tag][@digest]",
                                 param_hint=option)
    if match["digest"]:
        algorithm, separator, digest = match["digest"].partition(":")
        lengths = {"sha256": 64, "sha384": 96, "sha512": 128}
        if (not separator or algorithm not in lengths
                or not re.fullmatch(rf"[a-f0-9]{{{lengths[algorithm]}}}", digest)):
            raise click.BadParameter("expected a complete sha256, sha384 or sha512 hex digest",
                                     param_hint=option)
    return match


def namespace(value):
    """An output namespace may include registry/port and nested repository paths."""
    image_reference(f"{value}/dc-kos-image", "--namespace")


def source_ref(value, option):
    """Support branch/tag names safe for the recipe's shell and Makefile boundaries."""
    parts = value.split("/")
    if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", value)
            or ".." in value or value.endswith(".")
            or any(not part or part.startswith(".") or part.endswith(".lock") for part in parts)):
        raise click.BadParameter(
            "use a branch/tag containing letters, digits, dots, underscores, slashes or hyphens; "
            "empty/dot-prefixed components, '..', trailing dots and '.lock' suffixes are invalid",
            param_hint=option,
        )


def profile(value):
    """A profile is a basename in the selected checkout, not a path."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value) or ".." in value:
        raise click.BadParameter("expected a profile name, not a path", param_hint="--profile")
