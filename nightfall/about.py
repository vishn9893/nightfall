"""The installed version, read from package metadata.

One helper, because the number is wanted in two places that must not disagree:
the banner the user reads and the service version telemetry reports.
"""

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION = "nightfall-cli"

# A source tree with no install has no metadata to read, and the banner is not
# worth failing over.
UNKNOWN = "0.0.0"


def current() -> str:
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return UNKNOWN
