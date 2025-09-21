# Shorts-Bot PRO

Автоматизация подготовки и загрузки YouTube Shorts с серверным слоем FastAPI под Render.

## Переменные окружения
| Переменная | Назначение | Значение по умолчанию |
|------------|------------|------------------------|
| `ADMIN_TOKEN` | Bearer-токен для всех защищённых эндпоинтов | — |
| `TZ` | Таймзона исполнения заданий | `Asia/Almaty` |
| `YOUTUBE_API_KEY` | Ключ YouTube Data API v3 для поиска идей | — |
| `YOUTUBE_REGION` | Регион поиска трендов | `US` |
| `YT_SEARCH_QUERIES` | CSV-список поисковых запросов | — |
| `IDEAS_PER_REFRESH` | Лимит идей за один вызов `/ideas/refresh` | `50` |
| `YT_CLIENT_ID` | OAuth Client ID для загрузки видео | — |
| `YT_CLIENT_SECRET` | OAuth Client Secret | — |
| `YT_REFRESH_TOKEN` | OAuth Refresh Token с правом `youtube.upload` | — |
| `DEFAULT_TAGS` | CSV-теги по умолчанию для генерации/загрузки | — |
| `GOOGLE_TOKEN_URI` | Пользовательский OAuth token endpoint (опционально) | `https://oauth2.googleapis.com/token` |
| `YOUTUBE_CLIENT_SECRET_JSON` | (Легаси) JSON с OAuth client (auto-parse) | — |
| `YOUTUBE_TOKEN_JSON` | (Легаси) JSON с refresh_token (auto-parse) | — |

> ⚙️ **Совместимость:** сервис автоматически извлекает `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` из старых JSON переменных, если они заданы.

Файлы конфигурации:
- `config.yaml` — базовые параметры генерации (fps, разрешение, хэштеги и пр.).
- `config/topics.yaml` — список подготовленных тем.
- `data/input/topics_buffer.json` — накопительный буфер тем.

## Получение OAuth refresh_token
1. Зайдите в [Google OAuth Playground](https://developers.google.com/oauthplayground/).
2. В шаге 1 выберите **YouTube Data API v3** → `https://www.googleapis.com/auth/youtube.upload` и нажмите *Authorize APIs*.
3. В настройках (иконка шестерёнки) переключитесь на «Use your own OAuth credentials» и введите `YT_CLIENT_ID` и `YT_CLIENT_SECRET`.
4. После авторизации нажмите *Exchange authorization code for tokens* — в ответе появится `refresh_token`.
5. Сохраните `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` в Render → Environment Variables. Значение `ADMIN_TOKEN` задайте вручную (надёжная случайная строка).

Секреты хранятся только в переменных окружения Render; файл `config.yaml` можно настраивать через деплой, не добавляя в репозиторий приватные данные.

## Примеры вызова API
```bash
# health-check (без авторизации)
curl https://<host>/health

# обновление пула идей из YouTube
curl -X POST https://<host>/ideas/refresh \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"queries":["funny cats"],"region":"US","limit":10}'

# сохранение новых тем для генерации
curl -X POST https://<host>/trends/generate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topics":[{"title":"Тестовый ролик","lines":["крючок","факт","финал"],"tags":["shorts"]}]}'

# постановка тем в очередь и запуск генерации (без загрузки)
curl -X POST https://<host>/run/queue \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topics":"all","upload":false}'

# генерация и загрузка выбранных индексов
curl -X POST https://<host>/run/queue \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topics":[0,2],"upload":true}'
```

## Ограничения формата Shorts
- Видео должны быть вертикальными **1080×1920** или другим соотношением 9:16.
- Длительность — **не более 60 секунд**.
- При генерации следите за короткими фразами и хэштегами, чтобы ролики проходили модерацию.

## Запуск локально
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload
```

## Деплой на Render
`render.yaml` уже содержит конфигурацию Web Service: Python 3.11, команда запуска `uvicorn server:app --host 0.0.0.0 --port $PORT`. После установки переменных окружения запустите деплой — миграции не требуются.
