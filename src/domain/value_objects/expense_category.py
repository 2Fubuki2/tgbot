import enum


class ExpenseCategory(enum.StrEnum):
    PARTS = "parts"          # Запчасти
    FUEL = "fuel"            # Топливо
    EVENTS = "events"        # Мероприятия
    RENT = "rent"            # Аренда
    EQUIPMENT = "equipment"  # Экипировка
    FOOD = "food"            # Питание/посиделки
    TRANSPORT = "transport"   # Транспорт/логистика
    OTHER = "other"          # Прочее
