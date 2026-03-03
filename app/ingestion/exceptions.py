class IngestionException(Exception):
    """
    Base ingestion exception.
    All domain-level ingestion errors inherit from this.
    """
    pass


class InvalidSensorPayload(IngestionException):
    """
    Raised when business-level validation fails.
    (Not schema validation — that's handled by Pydantic.)
    """
    pass


class DeviceNotAuthorized(IngestionException):
    """
    Raised when device authentication fails.
    """
    pass


class DuplicateIngestion(IngestionException):
    """
    Raised when duplicate payload is detected.
    Reserved for future idempotency handling.
    """
    pass