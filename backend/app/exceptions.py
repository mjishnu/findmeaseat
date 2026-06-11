"""Domain errors. main.py maps AppError subclasses to JSON responses,
so services raise these without importing anything HTTP-specific."""


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
