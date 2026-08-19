class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class TrainNotFoundError(AppError):
    status_code = 404

    def __init__(self, train_number: str):
        super().__init__(f"Train {train_number} not found")


class InvalidStationError(AppError):
    """Station not on route, wrong direction, or source == destination."""


class InvalidJourneyDateError(AppError):
    """Date in the past or beyond the advance reservation period."""


class ManifestExpiredError(AppError):
    status_code = 404

    def __init__(self, detail: str = "Manifest expired or unknown"):
        super().__init__(detail)


class InvalidManifestError(AppError):
    """Invalid results payload or mismatch in manifest execution."""


class ProviderUnavailableError(AppError):
    """The upstream rail data source failed (network error, rate limit, or a
    persistent 'try again' response) after retries. Distinct from a train
    simply not existing, which degrades to TrainNotFoundError / a skipped pair."""

    status_code = 503

    def __init__(self, detail: str = "Rail data source is temporarily unavailable"):
        super().__init__(detail)
