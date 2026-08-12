# 🤖 TreasuryBot - Бот для управления бюджетом мотоклуба

**TreasuryBot** - это Telegram-бот для управления финансами мотоклуба: взносы, штрафы, платежи, расходы.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.7+-green.svg)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Возможности

### Для участников
- 📋 **Лицевой счёт** - просмотр долга, переплаты, истории
- 💰 **Мои платежи** - история всех платежей
- ⚠️ **Мои штрафы** - активные и оплаченные штрафы
- 💳 **Реквизиты** - куда оплачивать взносы
- 📤 **Я оплатил** - отправка подтверждения оплаты с чеком

### Для казначея
- 💰 **Начислить взносы** - автоматическое начисление всем участникам
- ⏳ **Подтвердить платежи** - просмотр и подтверждение/отклонение оплат
- 📋 **Все участники** - список с долгами и балансами
- 🔍 **Поиск участников** - быстрый поиск по имени/ID
- ⚠️ **Штрафы** - начисление и управление штрафами
- 💸 **Расходы клуба** - учёт расходов по категориям
- 📬 **Напоминания** - массовая рассылка должникам
- 📊 **Статистика** - баланс, долги, активность

### Для администратора
- 👥 **Пользователи** - добавление, удаление, изменение ролей
- ⚙️ **Настройки** - размер взноса, реквизиты, название клуба
- 📋 **Журнал** - аудит всех действий
- 📄 **Экспорт** - выгрузка данных в JSON
- Полный доступ к функциям казначея и участника

---

## 🆕 Что нового в версии 2.0?

- ✅ **Новая структура меню** - "Мой бюджет" / "Бюджет клуба" / "Управление"
- ✅ **Умная навигация** - кнопка "Назад" возвращает на предыдущий экран
- ✅ **Отмена действий** - можно прервать любой процесс
- ✅ **Улучшенные уведомления** - красивые сообщения о платежах и штрафах
- ✅ **Поддержка webhook** - для бесплатного хостинга на Railway/Render
- ✅ **Исправлены баги** - удалены дублирующиеся обработчики

[Полный список изменений →](CHANGELOG.md)

---

## 🚀 Быстрый старт

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/your-username/treasurybot.git
cd treasurybot
```

### 2. Установите зависимости

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Настройте окружение

Создайте файл `.env`:

```env
BOT_TOKEN=ваш_токен_от_@BotFather
ADMIN_IDS=ваш_telegram_id
DATABASE_URL=sqlite+aiosqlite:///./treasurybot.db
```

**Как получить токен:**
1. Найдите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot` и следуйте инструкциям
3. Скопируйте токен в `.env`

**Как узнать свой Telegram ID:**
1. Найдите [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте `/start`
3. Скопируйте `Id` в `.env`

### 4. Запустите бота

```bash
python main.py
```

Готово! Откройте бота в Telegram и отправьте `/start`.

---

## 🌐 Деплой на хостинг (бесплатно 24/7)

### Рекомендуется: Railway

**Railway** - лучший вариант для бесплатного хостинга Telegram ботов.

➡️ **[Подробная инструкция по деплою на Railway](DEPLOY_RAILWAY.md)**

**Преимущества:**
- ✅ $5 кредитов/месяц (хватает на 15-20 пользователей)
- ✅ Автодеплой из GitHub
- ✅ Удобные логи
- ✅ Работает 24/7

### Альтернатива: PythonAnywhere

➡️ **[Инструкция по деплою на PythonAnywhere](DEPLOY_PYTHONANYWHERE.md)**

⚠️ Бесплатный аккаунт PythonAnywhere имеет ограничения для webhook.

---

## 📁 Структура проекта

```
treasurybot/
├── src/
│   ├── domain/              # Бизнес-логика
│   │   ├── entities/        # Сущности (User, Payment, Fine...)
│   │   ├── value_objects/   # Перечисления (Role, Status...)
│   │   └── interfaces/      # Интерфейсы репозиториев
│   ├── infrastructure/      # База данных
│   │   ├── database/        # Модели SQLAlchemy
│   │   └── repositories/    # Реализация репозиториев
│   ├── presentation/        # Telegram Bot UI
│   │   ├── handlers/        # Обработчики команд и callback
│   │   ├── keyboards/       # Клавиатуры бота
│   │   ├── middleware/      # Middleware (навигация)
│   │   └── states/          # FSM состояния
│   ├── config/              # Настройки
│   └── main.py              # Точка входа (polling)
├── webhook.py               # Точка входа (webhook)
├── main.py                  # Запуск локально
├── requirements.txt         # Зависимости
├── .env.example             # Пример настроек
├── README.md                # Этот файл
├── CHANGELOG.md             # История изменений
├── DEPLOY_RAILWAY.md        # Инструкция по Railway
└── DEPLOY_PYTHONANYWHERE.md # Инструкция по PythonAnywhere
```

**Архитектура:** Clean Architecture (Domain → Infrastructure → Presentation)

---

## ⚙️ Настройки (.env)

| Переменная | Описание | Обязательно | Пример |
|---|---|---|---|
| `BOT_TOKEN` | Токен от @BotFather | ✅ | `123456:ABC-DEF1234...` |
| `ADMIN_IDS` | Telegram ID админов (через запятую) | ✅ | `123456789,987654321` |
| `DATABASE_URL` | Путь к базе данных | ❌ | `sqlite+aiosqlite:///./treasurybot.db` |
| `LOG_LEVEL` | Уровень логирования | ❌ | `INFO` |
| `TIMEZONE` | Часовой пояс | ❌ | `Europe/Moscow` |
| `USE_WEBHOOK` | Использовать webhook | ❌ | `false` |
| `WEBHOOK_DOMAIN` | Домен для webhook | ❌ | `https://mybot.railway.app` |
| `WEBAPP_HOST` | Хост веб-приложения | ❌ | `0.0.0.0` |
| `WEBAPP_PORT` | Порт веб-приложения | ❌ | `8000` |

---

## 📊 База данных

По умолчанию используется **SQLite** (файл `treasurybot.db`).

### Таблицы:
- `users` - пользователи (участники, казначеи, админы)
- `monthly_fees` - ежемесячные взносы
- `payments` - платежи (pending/confirmed/rejected)
- `fines` - штрафы
- `expenses` - расходы клуба
- `club_settings` - настройки (размер взноса, реквизиты)
- `audit_logs` - журнал действий

### Миграции

База создаётся автоматически при первом запуске.

Для сброса базы:
```bash
rm treasurybot.db
python main.py
```

---

## 🛠️ Разработка

### Запуск в режиме разработки

```bash
# Установите зависимости для разработки
pip install -r requirements.txt

# Запустите бота с автоперезагрузкой
python main.py
```

### Тестирование

```bash
# Проверка синтаксиса
python -m py_compile src/**/*.py

# Проверка типов (опционально)
pip install mypy
mypy src/
```

### Форматирование кода

```bash
pip install black
black src/
```

---

## 🤝 Вклад в проект

Буду рад вашим Pull Request! 

1. Форкните репозиторий
2. Создайте ветку (`git checkout -b feature/amazing-feature`)
3. Закоммитьте изменения (`git commit -m 'Add amazing feature'`)
4. Запушьте ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

---

## 📝 Лицензия

MIT License - см. [LICENSE](LICENSE)

---

## 💬 Поддержка

- 🐛 **Нашли баг?** → [Создайте Issue](https://github.com/your-username/treasurybot/issues)
- 💡 **Есть идея?** → [Создайте Feature Request](https://github.com/your-username/treasurybot/issues)
- ❓ **Вопросы?** → [Discussions](https://github.com/your-username/treasurybot/discussions)

---

## 🙏 Благодарности

- [Aiogram](https://docs.aiogram.dev/) - отличный фреймворк для Telegram ботов
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM для Python
- [Pydantic](https://docs.pydantic.dev/) - валидация данных
- [Railway](https://railway.app/) - бесплатный хостинг

---

**TreasuryBot** © 2026 | Создано с ❤️ для мотоклубов

⭐ Поставьте звезду, если проект был полезен!
