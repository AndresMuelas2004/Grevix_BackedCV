class IngestionError(Exception):
    """A CV or posting the app cannot read. Mapped to a 4xx response with a stable code."""

    def __init__(self, code: str, title: str, detail: str = "", status: int = 422):
        super().__init__(f"{code}: {title}")
        self.code = code
        self.title = title
        self.detail = detail
        self.status = status
