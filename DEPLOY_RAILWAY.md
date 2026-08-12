# 🚀 Деплой бота на Railway (РЕКОМЕНДУЕТСЯ)

Railway - это современная платформа для хостинга с бесплатным tier. Идеально подходит для Telegram ботов!

---

## ✅ Преимущества Railway

- ✅ **Бесплатно**: $5 кредитов в месяц (достаточно для 15-20 пользователей)
- ✅ **24/7**: Бот работает постоянно
- ✅ **Автодеплой**: При push в GitHub автоматически обновляется
- ✅ **Простая настройка**: 5 минут и бот в облаке
- ✅ **Логи**: Удобный просмотр логов в реальном времени

---

## 📋 Шаг 1: Подготовка

### 1.1 Создайте GitHub репозиторий

```bash
cd D:\tgbot

# Инициализируйте git (если еще не сделано)
git init
git add .
git commit -m "Initial commit"

# Создайте репозиторий на GitHub и залейте код
git remote add origin https://github.com/ваш-username/treasurybot.git
git branch -M main
git push -u origin main
```

### 1.2 Убедитесь, что есть файлы

- `requirements.txt` - список зависимостей
- `main.py` - точка входа для polling
- `webhook.py` - точка входа для webhook (необязательно)
- `.env.example` - пример конфигурации

---

## 🚀 Шаг 2: Деплой на Railway

### 2.1 Зарегистрируйтесь

1. Перейдите на https://railway.app
2. Нажмите **Start a New Project**
3. Войдите через GitHub

### 2.2 Создайте новый проект

1. Нажмите **New Project**
2. Выберите **Deploy from GitHub repo**
3. Выберите репозиторий `treasurybot`
4. Railway автоматически определит Python проект

### 2.3 Настройте переменные окружения

В разделе **Variables** добавьте:

```env
BOT_TOKEN=ваш_токен_от_botfather
ADMIN_IDS=ваш_telegram_id
DATABASE_URL=sqlite+aiosqlite:///./treasurybot.db
USE_WEBHOOK=false
```

**Важно**: Если у вас несколько админов, укажите через запятую:
```
ADMIN_IDS=123456789,987654321
```

### 2.4 Настройте команду запуска

Railway автоматически использует `main.py`, но можно указать явно:

1. Перейдите в **Settings** → **Deploy**
2. В **Start Command** укажите:
```bash
python main.py
```

---

## ✅ Шаг 3: Запуск и проверка

### 3.1 Деплой

Railway автоматически начнет деплой. Ждите ~2-3 минуты.

### 3.2 Проверьте логи

1. Перейдите в **View Logs**
2. Вы должны увидеть:
```
Starting TreasuryBot...
Creating database tables...
Database tables created successfully.
```

### 3.3 Протестируйте бота

Откройте вашего бота в Telegram и отправьте `/start`. Бот должен ответить!

---

## 🔄 Шаг 4: Автообновление

Теперь при каждом `git push` Railway автоматически обновит бота:

```bash
cd D:\tgbot
git add .
git commit -m "Update bot"
git push
```

Railway автоматически:
1. Заберет новый код
2. Установит зависимости
3. Перезапустит бота

---

## 🌐 Вариант с Webhook (опционально)

Если хотите использовать webhook вместо polling:

### 4.1 Обновите переменные окружения

```env
USE_WEBHOOK=true
WEBHOOK_DOMAIN=https://ваш-проект.up.railway.app
```

### 4.2 Измените команду запуска

```bash
python webhook.py
```

### 4.3 Получите домен Railway

1. В Railway перейдите в **Settings** → **Networking**
2. Нажмите **Generate Domain**
3. Скопируйте домен (например: `treasurybot-production.up.railway.app`)
4. Добавьте в переменные: `WEBHOOK_DOMAIN=https://treasurybot-production.up.railway.app`

---

## 💾 База данных

По умолчанию используется SQLite (файл `treasurybot.db`).

**⚠️ Важно**: При рестарте Railway SQLite файл **НЕ теряется**, если используете volume:

1. Перейдите в **Settings** → **Volumes**
2. Добавьте volume: Mount Path = `/app`
3. Теперь база данных сохраняется между деплоями

---

## 📊 Мониторинг

### Просмотр логов

```bash
# В Railway нажмите "View Logs"
# Или установите CLI:
npm i -g @railway/cli
railway login
railway logs
```

### Рестарт бота

1. В Railway перейдите в **Deployments**
2. Нажмите **Restart**

---

## 🆘 Частые проблемы

### Бот не запускается

**Проблема**: В логах `ModuleNotFoundError`

**Решение**: Проверьте `requirements.txt`:
```bash
# В Railway перейдите в Settings → Deploy
# Убедитесь, что установлены все зависимости
```

### База данных теряется

**Проблема**: После рестарта все пользователи пропадают

**Решение**: Добавьте Volume (см. раздел "База данных")

### Бот не отвечает

**Проблема**: Бот онлайн, но не отвечает

**Решение**: 
1. Проверьте логи в Railway
2. Убедитесь, что `BOT_TOKEN` правильный
3. Проверьте, что бот не запущен локально одновременно

---

## 💰 Лимиты бесплатного плана

- **$5** кредитов в месяц
- **500 часов** выполнения
- **1 GB** RAM
- **1 GB** хранилища

Для 15-20 пользователей этого **более чем достаточно**! 🚀

---

## 🔐 Безопасность

**Никогда не коммитьте `.env` в GitHub!**

Убедитесь, что в `.gitignore` есть:
```
.env
treasurybot.db
__pycache__/
*.pyc
.venv/
```

---

## 📚 Дополнительные команды

### Просмотр переменных окружения

В Railway: **Variables** → список всех переменных

### Удаление проекта

**Settings** → **Danger** → **Delete Service**

---

## 🎉 Готово!

Ваш бот теперь работает 24/7 бесплатно на Railway! 

**Что дальше?**
- Пригласите участников клуба
- Настройте размер взноса через бота
- Добавьте реквизиты для оплаты

**Нужна помощь?** Пишите в Issues на GitHub!

---

## 🔗 Полезные ссылки

- Railway: https://railway.app
- Документация Railway: https://docs.railway.app
- Aiogram документация: https://docs.aiogram.dev
- Исходный код бота: https://github.com/ваш-username/treasurybot
