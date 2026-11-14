"""Hostname redaction uses generic patterns and remains stable on repeated scrubs."""

import pytest

from scripts.privacy.scrub import scrub_text


@pytest.mark.parametrize("platform", ["linux", "mac"])
def test_platform_hostname_scrub_is_generic_and_idempotent(platform):
    text = f"Connected to sample-workstation-{platform}."
    scrubbed = scrub_text(text)
    assert scrubbed == f"Connected to ghost-dev-{platform}."
    assert scrub_text(scrubbed) == scrubbed
