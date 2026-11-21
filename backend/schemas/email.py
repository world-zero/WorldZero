from schemas.base import WireModel


class UnsubscribeOut(WireModel):
    """The event key whose email was turned off (the page names it)."""

    event: str
