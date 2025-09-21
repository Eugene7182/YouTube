# Shorts-Bot PRO

Автоматизация подготовки и загрузки YouTube Shorts. Бэкенд построен на FastAPI, MoviePy и gTTS, поддерживает OAuth 2.0 загрузку и ручное управление темами.

## Переменные окружения

| Переменная | Назначение | Пример |
|------------|------------|--------|
| `ADMIN_TOKEN` | Опциональный bearer-токен для прод-режима. Если не задан, API работает в dev-режиме без авторизации | `super-secret-token` |
| `TZ` | Базовая таймзона процесса (используется как дефолт для расписаний) | `Asia/Almaty` |
| `YOUTUBE_API_KEY` | Ключ YouTube Data API v3 для поиска идей | `AIza...` |
| `YOUTUBE_REGION` | Регион поиска трендов | `US` |
| `YT_SEARCH_QUERIES` | CSV-список поисковых запросов по умолчанию | `cats,dogs` |
| `IDEAS_PER_REFRESH` | Лимит идей на запрос `/ideas/refresh` | `25` |
| `DEFAULT_TAGS` | CSV тегов, которые добавляются к каждому ролику | `#shorts,#fun` |
| `YOUTUBE_CLIENT_SECRET_JSON` | Client secret JSON (строка) из Google Cloud | `{"web":{...}}` |
| `YOUTUBE_CLIENT_SECRET_FILE` | Путь до `client_secret.json` (альтернатива предыдущему) | `/etc/secrets/client_secret.json` |
| `YT_CLIENT_ID` / `YT_CLIENT_SECRET` | Пара OAuth-клиента (если не используется JSON) | `123.apps.googleusercontent.com` |
| `YT_REFRESH_TOKEN` | Refresh token со scope `youtube.upload` | `1//0g...` |
| `YOUTUBE_TOKEN_JSON` | JSON c refresh_token (извлекается автоматически) | `{"refresh_token":"..."}` |
| `GOOGLE_TOKEN_URI` | Кастомный OAuth token endpoint (опционально) | `https://oauth2.googleapis.com/token` |

> ⚙️ Сервис автоматически подтянет `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` из `YOUTUBE_CLIENT_SECRET_JSON`, `YOUTUBE_CLIENT_SECRET_FILE` и `YOUTUBE_TOKEN_JSON`, если они заданы. Секреты и токены никогда не логируются.

## Как получить client_secret.json и refresh_token

1. Создайте OAuth-клиент типа *Desktop App* или *Web application* в [Google Cloud Console](https://console.cloud.google.com/apis/credentials) для проекта с включённым YouTube Data API v3.
2. Скачайте `client_secret.json` и сохраните путь в `YOUTUBE_CLIENT_SECRET_FILE` **или** вставьте содержимое целиком в `YOUTUBE_CLIENT_SECRET_JSON`.
3. Зайдите в [Google OAuth Playground](https://developers.google.com/oauthplayground/), откройте шестерёнку, включите «Use your own OAuth credentials» и вставьте `YT_CLIENT_ID` и `YT_CLIENT_SECRET`.
4. На шаге 1 выберите scope `https://www.googleapis.com/auth/youtube.upload`, авторизуйтесь и выполните *Exchange authorization code for tokens*.
5. Сохраните `refresh_token` в `YT_REFRESH_TOKEN` (или целиком ответ в `YOUTUBE_TOKEN_JSON`).

## Основные файлы

- `config.yaml` — базовые настройки генерации (шрифты, разрешение, теги, авторасписание).
- `config/topics.yaml` — основной список тем для генерации.
- `data/input/topics_buffer.json` — буфер уникальных тем, сохраняемый через `/trends/generate`.

## Примеры API-запросов

```bash
# Проверка здоровья сервиса
curl https://<host>/health

# Добавление новых тем (две темы, у второй расписание в локальной зоне +06:00)
curl -X POST https://<host>/trends/generate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topics": [
      {
        "title": "Почему коты любят коробки",
        "lines": ["Интрига", "Факт", "Вывод"],
        "tags": ["cats", "fun"],
        "schedule": "2025-09-22T21:00:00+06:00"
      },
      {
        "title": "5 привычек для продуктивности",
        "lines": ["Привычка 1", "Привычка 2", "Финал"],
        "tags": ["productivity"]
      }
    ]
  }'

# Запуск генерации и загрузки всех тем
curl -X POST https://<host>/run/queue \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topics": "all", "upload": true}'

# Запуск только выбранных тем по индексам без загрузки
curl -X POST https://<host>/run/queue \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topics": [0, "5 привычек для продуктивности"], "upload": false}'
```

> 🕒 Если `schedule` не задан, а в `config.yaml` включено `uploader.auto_schedule_if_missing`, система автоматически распишет ближайший слот `uploader.time_local` в зоне `uploader.timezone` (по умолчанию `Asia/Almaty`).

## Ограничения YouTube Shorts

- Соотношение сторон 9:16 (например, 1080×1920).
- Длительность ≤ 60 секунд.
- Используйте короткие цепляющие реплики и релевантные теги, чтобы пройти модерацию.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 10000 --reload
```

## Деплой на Render

- Стартер команды: `uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}`.
- Перед деплоем выставьте все секреты в разделе Environment Variables.
- ffmpeg берётся из `imageio-ffmpeg`, поэтому отдельная установка не требуется. Ошибки кодеков выводятся в виде понятных сообщений.
