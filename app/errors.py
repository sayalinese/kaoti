class AppError(Exception):
    status = 400


class InvalidInput(AppError):
    status = 400


class NotFound(AppError):
    status = 404


class Conflict(AppError):
    status = 409
