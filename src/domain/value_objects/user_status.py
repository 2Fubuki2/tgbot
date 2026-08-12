import enum


class UserStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPELLED = "expelled"
