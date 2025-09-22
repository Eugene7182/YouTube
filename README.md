# Shorts-Bot PRO

Автоматизация генерации и загрузки YouTube Shorts на базе FastAPI, MoviePy и официального YouTube API. Репозиторий настроен на полностью безсерверный поток: ежедневные тренды подмешиваются в контент-план, очередь роликов собирается и загружается автоматически.

## Переменные окружения

| Переменная | Назначение | Значение по умолчанию |
|------------|------------|------------------------|
| `YOUTUBE_CLIENT_SECRET_JSON` | Inline JSON client_secret.json (OAuth Desktop) | — |
| `YOUTUBE_TOKEN_JSON` | Inline JSON token.json (authorized_user c refresh_token) | — |
| `YOUTUBE_API_KEY` | Ключ YouTube Data API v3 для чтения трендов | — |
| `CHANNEL_DEFAULT_TAGS` | Базовые теги (CSV), максимум 3 | `shorts,cartoon,comedy` |
| `DEFAULT_CATEGORY_ID` | Категория YouTube по умолчанию | `1` |
| `DEFAULT_PRIVACY` | Статус загрузки без расписания | `private` |
| `TZ_TARGET` | Целевая таймзона публикации | `America/New_York` |
| `TZ_LOCAL` | Локальная таймзона процесса | `Asia/Almaty` |
| `SERVICE_BASE_URL` | Публичный URL API (для cron/Actions) | `https://shorts-api.onrender.com` |
| `ADMIN_TOKEN` | Bearer-токен для админ эндпоинтов | — |
| `RENDER_DEPLOY` | Маркер исполнения на Render | `1` |
| `YOUTUBE_DRY_RUN` | `1` = не отправлять загрузку, только лог | `0` |

Дополнительно поддерживаются `YOUTUBE_REGION`, `YT_SEARCH_QUERIES`, `IDEAS_PER_REFRESH` для тонкой настройки поиска идей.

`.env.example` содержит готовый шаблон с подсказками по заполнению.

## OAuth без локального запуска

1. В [Google Cloud Console](https://console.cloud.google.com/apis/credentials) создайте OAuth-клиент *Desktop app*. Экспортируйте `client_secret.json`, откройте его и скопируйте содержимое целиком в `YOUTUBE_CLIENT_SECRET_JSON` (inline JSON). При необходимости отредактируйте файл согласия (OAuth consent screen) и переведите его в статус *In production* — иначе refresh-token перестанет работать спустя несколько дней.
2. Перейдите в [Google OAuth Playground](https://developers.google.com/oauthplayground/). В настройках (иконка шестерёнки) включите «Use your own OAuth credentials» и вставьте `client_id`/`client_secret` из предыдущего шага.
3. На шаге 1 Playground выберите scope `https://www.googleapis.com/auth/youtube.upload`, авторизуйтесь и выполните *Exchange authorization code for tokens*.
4. В блоке `Step 2` нажмите «Download JSON» — полученный payload вставьте в `YOUTUBE_TOKEN_JSON`. Убедитесь, что поле `refresh_token` присутствует.
5. После сохранения переменных перезапустите сервис (Render автоматически применит новые значения). Код валидирует JSON при старте и выводит понятные сообщения об ошибках.

## Эндпоинты

- `POST /trends/generate` — принимает `{"topics": [...]}` и сохраняет темы в `config/topics.yaml` + буфер.
- `POST /run/queue` — запускает пайплайн MoviePy/tts, валидирует метаданные, проверяет длительность и соотношение сторон, при `upload=true` вызывает YouTube uploader. Ответ содержит список загруженных роликов со статусами и `videoId`.

Базовый health-check: `GET /health`. Документация: `GET /docs`.

### Быстрый старт через Swagger UI

1. Перейдите на `/docs`, нажмите **Authorize** и вставьте `ADMIN_TOKEN`, если он задан.
2. В секции **/trends/generate** нажмите **Try it out** и вставьте пример:
   ```json
   {
     "topics": [
       {
         "title": "Test topic",
         "lines": ["Hook", "Twist"],
         "tags": ["shorts", "demo"]
       }
     ]
   }
   ```
   После **Execute** должно вернуться `{ "count": 1 }`.
3. В секции **/run/queue** вызовите эндпоинт с телом `{"topics": "all", "upload": true, "dry_run": true}` — сервис выполнит сборку, но пропустит фактическую загрузку. Ответ содержит `status: "ok"` и `produced` ≥ 1.
4. Для реального аплоада снимите `dry_run` и повторите вызов; при успешном аплоаде в логах появится `videoId`, а в ответе — статус `uploaded`.

## Ротация расписания

- `scripts/seed_month.py` генерирует 3×N тем (Hook/Setup/Twist) с расписанием по слотам. Можно вызвать `python scripts/seed_month.py --start 2025-01-01 --days 30 --slots "09:00,15:00,20:00"`.
- `tasks/fetch_trending_shorts.py` берёт US Shorts через `videos.list?chart=mostPopular`, фильтрует длительность ≤ 60 секунд и записывает идеи в очередь без расписания.
- `tasks/run_queue.py` дергает `/run/queue` с нужными параметрами (`--upload` включает фактическую загрузку).

Все скрипты читают `SERVICE_BASE_URL` и `ADMIN_TOKEN`, поэтому могут работать как локально, так и из GitHub Actions/Render cron.

## Хуки/лупы

- **Render cron** (описан в `render.yaml`):
  - `daily-fetch-trends` (12:00 UTC) — пополняет идеи заранее.
  - `daily-run-queue` (13:00 UTC = 09:00 ET летом) — генерирует и загружает новый шорт.
  - `seed-month-once` — опциональный одноразовый job для заполнения контент-плана.
- **YouTube uploader** автоматически делает retry при ошибках 429/5xx и всегда логирует `videoId`. Если `publishAt` пришёл в прошлом или ближе чем через 60 минут — время сдвигается вперёд, статус остаётся `private` до публикации.
- Все временные файлы рендерятся в `/tmp/shorts-output` и удаляются сразу после аплоада.

## Бесплатный деплой на Render

1. В панели Render создайте **Blueprint** и укажите путь к `render.yaml` из репозитория.
2. В разделе Environment добавьте переменные окружения из `.env.example`. JSON-значения вставляйте целиком (с кавычками).
3. После деплоя web-сервис `shorts-api` будет слушать порт `10000`, cron jobs автоматически активируются.
4. `SERVICE_BASE_URL` должен указывать на публичный URL сервиса (например, `https://shorts-api.onrender.com`). Cron job'ы и GitHub Actions используют его для вызова API.

## GitHub Actions: ручной запуск

Workflow `.github/workflows/ops.yml` позволяет управлять процессом без доступа к Render cron:

1. Откройте вкладку **Actions → Ops → Run workflow**.
2. Укажите при необходимости `seed_month_start`, количество дней и слот (по умолчанию 09:00 ET).
3. Выберите чекбоксы `Fetch trends` / `Run queue`.
4. Нажмите **Run workflow** — GitHub Actions выполнит соответствующие скрипты (`tasks/*.py`).

Требуемые Secrets в GitHub:
- `YOUTUBE_CLIENT_SECRET_JSON`
- `YOUTUBE_TOKEN_JSON`
- `YOUTUBE_API_KEY`
- `CHANNEL_DEFAULT_TAGS`
- `DEFAULT_CATEGORY_ID`
- `DEFAULT_PRIVACY`
- `TZ_TARGET`
- `TZ_LOCAL`
- `SERVICE_BASE_URL`
- `ADMIN_TOKEN`

## Monthly topics (free)

1. В разделе **Settings → Secrets and variables → Actions** добавьте секреты:
   - `BASE_URL` = `https://<render>.onrender.com`
   - `ADMIN_TOKEN` = `sbp_admin_…`
   Эти значения считываются `scripts/seed_month.py`; без них скрипт сохраняет `topics_month.json` локально и подсказывает отправить payload вручную.
2. Workflow `.github/workflows/seed-monthly.yml` запускается автоматически 1-го числа каждого месяца в 12:00 UTC и вызывает `python scripts/seed_month.py --days 30 --slots "09:00,15:00,20:00"`. Логи Actions фиксируют успешный POST на `/trends/generate` (ожидаемый ответ `{"count": N}`).
3. Для ручного запуска откройте **Actions → Seed monthly topics now → Run workflow**. Поле `start` можно оставить пустым (тогда скрипт возьмёт «завтра по ET») либо указать дату в формате `YYYY-MM-DD`.
4. После сидирования сервис берёт темы из очереди и собирает ролики через `/run/queue`. Можно ждать ежедневный workflow `post-daily.yml` либо вызвать вручную:
   ```bash
   curl -X POST "$BASE_URL/run/queue" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"topics": "scheduled", "upload": true}'
   ```

## Без Render Cron

1. Задайте `BASE_URL` и `ADMIN_TOKEN` в GitHub: перейдите в **Settings → Secrets and variables → Actions**, создайте одноимённые элементы (секреты или переменные) и вставьте значения из вашего деплоя API.
2. Для мгновенного заполнения очереди запустите workflow **Actions → Seed monthly topics now → Run workflow**. Поле `start` оставьте пустым для автоподстановки «завтра по ET» либо введите дату в формате `YYYY-MM-DD`.
3. Workflow `seed-monthly.yml` каждое первое число месяца в 12:00 UTC сам создаёт 90 тем (3 слота × 30 дней: 09:00, 15:00, 20:00 ET).
4. Workflow `post-daily.yml` ежедневно в 13:00 UTC вызывает `/run/queue` с загрузкой. Логи содержат ответ сервиса; при ошибке job завершается с понятным сообщением.

## Локальный запуск и dry-run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 10000 --reload
```

Для тестового прогона загрузчика задайте `YOUTUBE_DRY_RUN=1` — тело запроса будет залогировано без обращения к API.

## Проверка перед коммитом

- `ruff check .`
- `flake8`
- `pytest`

Smoke-тест `pytest` включает валидацию OAuth JSON, преобразование таймзон и dry-run очереди.
