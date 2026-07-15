"""BuildError — raised when a required manifest field is missing."""


class BuildError(Exception):
    """
    Raised during document assembly when a required manifest or profile
    field is empty and a renderer cannot produce a valid deliverable
    without it.

    Example::

        raise BuildError("manifest field 'system_name' is required by the cover renderer")
    """
