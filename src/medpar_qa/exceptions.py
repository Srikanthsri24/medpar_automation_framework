class MedparQAError(Exception):
    """Base framework exception."""


class InputReadError(MedparQAError):
    """Raised when an input file cannot be read."""


class ManifestError(MedparQAError):
    """Raised when the run manifest is invalid."""


class ValidationConfigurationError(MedparQAError):
    """Raised when a business rule lacks required configuration."""
