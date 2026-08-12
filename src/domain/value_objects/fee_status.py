import enum


class FeeStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    WAIVED = "waived"
