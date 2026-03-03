class HealthException(Exception):
    """Base exception for the health domain."""
    pass


class AnalysisError(HealthException):
    """Raised when the OpenAI analysis call fails or returns unusable data."""
    pass


class TooManyImages(HealthException):
    """Raised when the caller provides more images than allowed."""
    pass
