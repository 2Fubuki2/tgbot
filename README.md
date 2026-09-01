# TreasuryBot

Telegram-бот для управления финансами мотоклуба: взносы, платежи, штрафы, расходы.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-green.svg)](https://docs.aiogram.dev/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## Возможности

### Участники
- 📋 **Лицевой счёт** — баланс, история взносов, платежей, штрафов
- 💳 **Реквизиты** — куда переводить деньги
- 📤 **Я оплатил** — отправить подтверждение с чеком (inline-выбор месяца)
- ⚠️ **Мои штрафы** — активные и оплаченные

### Казначей
- 💰 **Начислить взносы** — всем участникам, на текущий или произвольный период
- ⏳ **Подтвердить платежи** — просмотр, подтверждение / отклонение с комментарием
- 💸 **Частичная оплата** — поддержка `paid_amount`, FIFO-погашение oldest-first
- 🔴 **Просроченные платежи** — экран с бейджами по возрасту долга (15 / 21 / 30 дней)
- 📬 **Напоминания** — массовая рассылка должникам с rate limiting
- ⚠️ **Штрафы** — начисление, оплата, отмена, allocation (распределение по периодам)
- 📊 **Статистика** — баланс клуба, долги, активность
- 📅 **Хронология** — timeline всех финансовых событий
- 💸 **Расходы клуба** — учёт по категориям, редактирование, удаление
- ✏️ **Журнал** — редактирование и удаление платежей / штрафов / взносов с перерасчётом балансов

### Администратор
- 👥 **Пользователи** — добавление, удаление, архивация, смена роли, переименование
- ⚙️ **Настройки** — размер взноса, реквизиты, название клуба, день автоначисления
- 📄 **Экспорт** — выгрузка данных в JSON / PDF
- 🔧 **Коррекция казны** — ручной сдвиг баланса
- 📋 **Журнал** — аудит всех действий

### Общее
- 🧭 **Умная навигация** — кнопка «Назад», история до 10 экранов
- 🚫 **Отмена** — `/cancel` в любом процессе
- 🌐 **Webhook + polling** — `main.py` для локальной разработки, `webhook.py` для прода
- 🕐 **MSK timezone** — все даты через `now_msk()` / `today_msk()`

---

## Роли

| Роль | Доступ |
|---|---|
| `MEMBER` | Личный кабинет, оплата, реквизиты |
| `TREASURER` | Всё выше + казначейские функции |
| `ADMIN` | Всё выше + пользователи, настройки, экспорт, журнал |

---

## Стек

- **Фреймворк:** aiogram 3.x
- **ORM:** SQLAlchemy 2.x (async)
- **БД:** aiosqlite (dev) / asyncpg (prod — Railway)
- **Миграции:** alembic
- **Конфиг:** pydantic-settings
- **PDF:** reportlab
- **Тесты:** pytest + pytest-asyncio

## Архитектура

Clean Architecture — три слоя:

```
src/
├── domain/              # Сущности, value objects, интерфейсы репозиториев
├── infrastructure/      # SQLAlchemy models, репозитории, timezone
└── presentation/        # Handlers, keyboards, middleware, FSM states
```

---

## Быстрый старт

```bash
git clone <repo-url> && cd tgbot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Создайте `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_IDS=ваш_telegram_id
DATABASE_URL=sqlite+aiosqlite:///./treasurybot.db
```

Запуск:

```bash
python main.py
```

---

## Деплой

Рекомендуется **Railway** — $5 кредита/месяц, автодеплой из GitHub, webhook 24/7.

- [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md)
- [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md)

---

## Тесты

```bash
python -m pytest
```

9 тестовых файлов, ~30 тестов. Критический: `test_keyboard_callback_routes.py` — проверяет, что каждый callback клавиатуры имеет handler.

---

## Структура проекта

```
treasurybot/
├── src/
│   ├── domain/              # Бизнес-логика
│   ├── infrastructure/      # БД, репозитории
│   ├── presentation/        # Handlers, keyboards, middleware
│   └── config/              # Settings, logger
├── alembic/                 # Миграции
├── tests/                   # Тесты
├── main.py                  # Polling (dev)
├── webhook.py               # Webhook (prod)
├── requirements.txt
├── .env.example
└── README.md
```

---

## License

MIT
