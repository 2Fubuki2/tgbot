# 🚀 Деплой бота на PythonAnywhere (бесплатно)

Эта инструкция поможет вам развернуть TreasuryBot на PythonAnywhere для работы 24/7.

---

## 📋 Предварительные требования

1. **Зарегистрируйтесь на PythonAnywhere**
   - Перейдите на https://www.pythonanywhere.com
   - Создайте бесплатный аккаунт (Beginner)

2. **Получите Telegram Bot Token**
   - Найдите @BotFather в Telegram
   - Создайте бота: `/newbot`
   - Сохраните токен

3. **Настройте публичный домен**
   - На бесплатном аккаунте: `https://yourusername.pythonanywhere.com`

---

## 🔧 Шаг 1: Подготовка проекта

### 1.1 Обновите settings.py

Добавьте в `src/config/settings.py`:

```python
class Settings(BaseSettings):
    # ... существующие поля ...
    
    # Webhook settings
    webhook_domain: str = Field(default="", env="WEBHOOK_DOMAIN")
    # Пример: https://yourusername.pythonanywhere.com
```

### 1.2 Создайте .env для PythonAnywhere

Создайте файл `.env.production`:

```env
BOT_TOKEN=ваш_токен_от_botfather
ADMIN_IDS=ваш_telegram_id,другой_админ_id
DATABASE_URL=sqlite+aiosqlite:///./treasurybot.db
WEBHOOK_DOMAIN=https://yourusername.pythonanywhere.com
```

Замените `yourusername` на ваш логин PythonAnywhere!

---

## 🚀 Шаг 2: Загрузка на PythonAnywhere

### 2.1 Откройте консоль Bash

В PythonAnywhere: `Consoles` → `Bash`

### 2.2 Загрузите проект

**Вариант А: Через Git (рекомендуется)**

```bash
cd ~
git clone https://github.com/your-repo/treasurybot.git
cd treasurybot
```

**Вариант Б: Через Files**

1. Перейдите в `Files` на PythonAnywhere
2. Загрузите все файлы проекта
3. В консоли:
```bash
cd ~/treasurybot
```

### 2.3 Установите зависимости

```bash
# Создайте виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

### 2.4 Настройте .env

```bash
# Скопируйте и отредактируйте .env
cp .env.example .env
nano .env
```

Вставьте настройки из `.env.production` и сохраните (Ctrl+O, Enter, Ctrl+X).

---

## 🌐 Шаг 3: Настройка Web App

### 3.1 Создайте Web App

1. Перейдите в `Web` на PythonAnywhere
2. Нажмите `Add a new web app`
3. Выберите `Manual configuration`
4. Выберите `Python 3.11`

### 3.2 Настройте WSGI файл

1. В разделе `Code` найдите `WSGI configuration file`
2. Кликните на файл (например: `/var/www/yourusername_pythonanywhere_com_wsgi.py`)
3. **Удалите всё содержимое** и замените на:

```python
import sys
import os

# Добавляем путь к проекту
path = '/home/yourusername/treasurybot'
if path not in sys.path:
    sys.path.append(path)

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv(os.path.join(path, '.env'))

# ВАЖНО: aiohttp приложение, а не WSGI!
# PythonAnywhere не поддерживает ASGI напрямую, поэтому используем uvicorn
from webhook import main
application = main
```

⚠️ **Замените `yourusername` на ваш логин!**

### 3.3 Настройте виртуальное окружение

В разделе `Virtualenv` укажите:
```
/home/yourusername/treasurybot/venv
```

---

## ⚙️ Шаг 4: Альтернативный способ (через Always-On Task)

Бесплатный аккаунт PythonAnywhere не поддерживает долгоживущие процессы в Web Apps, но есть обходной путь:

### 4.1 Используйте Scheduled Task

1. Перейдите в `Tasks`
2. Создайте задачу, которая запускается **каждые 5 минут**:

```bash
cd /home/yourusername/treasurybot && source venv/bin/activate && python webhook.py > /tmp/bot.log 2>&1 &
```

Но это **не рекомендуется** для webhook!

### 4.2 Лучший вариант: используйте polling для бесплатного аккаунта

Если webhook не работает, используйте polling:

1. Создайте scheduled task на каждый день в 00:00:
```bash
cd /home/yourusername/treasurybot && source venv/bin/activate && python main.py
```

2. Или используйте сервис типа **Railway**, **Render**, **Fly.io** для бесплатного хостинга с webhook.

---

## 🔍 Шаг 5: Проверка и отладка

### 5.1 Проверьте логи

```bash
# В консоли PythonAnywhere
cd ~/treasurybot
source venv/bin/activate
python webhook.py
```

Если ошибок нет, бот должен запуститься.

### 5.2 Проверьте webhook

```bash
curl https://yourusername.pythonanywhere.com/bot/YOUR_BOT_TOKEN
```

Должен вернуть 404 или ответ от бота.

### 5.3 Протестируйте в Telegram

Откройте бота в Telegram и отправьте `/start`.

---

## 📝 Важные замечания для бесплатного аккаунта

⚠️ **Ограничения бесплатного PythonAnywhere:**

1. **Нет поддержки долгоживущих процессов** - Web App работает только при запросах
2. **Нет webhook с постоянным соединением** - нужен платный аккаунт ($5/месяц)
3. **Ограничение CPU** - 100 секунд в день

### 🎯 Альтернативы для бесплатного 24/7 хостинга:

1. **Railway** (https://railway.app) - 500 часов бесплатно/месяц
2. **Render** (https://render.com) - бесплатный tier с автосном через 15 мин
3. **Fly.io** (https://fly.io) - бесплатно с ограничениями
4. **Heroku альтернативы** - Clever Cloud, Back4App

---

## 🔄 Обновление бота

```bash
cd ~/treasurybot
git pull  # если используете git
source venv/bin/activate
pip install -r requirements.txt
# Перезапустите web app через интерфейс PythonAnywhere
```

---

## 🆘 Частые проблемы

### Webhook не работает

```bash
# Проверьте, установлен ли webhook
curl https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo
```

### База данных не создается

```bash
cd ~/treasurybot
source venv/bin/activate
python -c "from src.main import on_startup; import asyncio; asyncio.run(on_startup())"
```

### Бот не отвечает

1. Проверьте логи в `Error log` на странице Web App
2. Проверьте, что `.env` содержит правильный токен
3. Убедитесь, что домен в `WEBHOOK_DOMAIN` совпадает с URL Web App

---

## 💡 Рекомендации

Для **бесплатного 24/7** рекомендую использовать **Railway** или **Render** вместо PythonAnywhere.

**Инструкция для Railway** будет в следующем файле `DEPLOY_RAILWAY.md` 🚀
