import enum


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
