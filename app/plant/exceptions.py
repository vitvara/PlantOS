class PlantException(Exception):
    """Base exception for the plant domain."""
    pass


class PlantNotFound(PlantException):
    """Raised when a plant record does not exist."""
    pass


class DeviceAlreadyRegistered(PlantException):
    """Raised when a device_id is already bound to a plant."""
    pass


class UnsupportedImageFormat(PlantException):
    """Raised when an uploaded file has an unsupported extension."""
    pass


class NoProfileImage(PlantException):
    """Raised when species ID is requested but the plant has no profile photo."""
    pass


class SpeciesIdentificationError(PlantException):
    """Raised when the OpenAI species identification call fails."""
    pass
