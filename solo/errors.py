class SoloError(Exception):
    """Base exception for user-facing SOLO failures."""


class NotFoundError(SoloError):
    """Raised when a project, workflow, action, or run cannot be found."""


class ValidationError(SoloError):
    """Raised when project-owned workflow data is invalid."""
