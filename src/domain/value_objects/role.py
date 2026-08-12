import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    TREASURER = "treasurer"
    MEMBER = "member"
