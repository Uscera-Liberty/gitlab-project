# Users CRUD API

Небольшой REST-сервис для управления пользователями: создание, чтение, обновление и удаление (CRUD).
Сервис упакован в Docker-образ (multi-stage сборка). GitLab CI его тестирует, собирает, публикует
в GitLab Container Registry и деплоит на сервер по SSH.

- **Стек:** Python 3.12, FastAPI, Uvicorn, SQLite, Pydantic, pytest, ruff
- **Данные:** SQLite-файл `/data/users.db` внутри контейнера, лежит в Docker volume, поэтому переживает перезапуск и передеплой
- **Стартовые данные:** при первом запуске в базу добавляются 4 пользователя (Alice — admin, Bob, Carol, Dave — user)

## Структура проекта

```
app/
  main.py          # FastAPI-приложение и все эндпоинты
  db.py            # подключение к SQLite, создание таблицы, стартовые пользователи
  models.py        # Pydantic-схемы: UserCreate, UserUpdate, User
tests/
  test_users.py    # 12 тестов на все операции и ошибки (404, 409, 422)
requirements.txt       # зависимости для работы сервиса
requirements-dev.txt   # + зависимости для тестов и линтера
pyproject.toml         # настройки ruff и pytest
Dockerfile             # multi-stage: builder -> test -> runtime
docker-compose.yml     # запуск одной командой
.gitlab-ci.yml         # пайплайн GitLab CI
```

## API

| Метод    | Путь          | Что делает                                    | Ответы             |
|----------|---------------|-----------------------------------------------|--------------------|
| `GET`    | `/health`     | проверка, что сервис жив                      | 200                |
| `GET`    | `/users`      | список пользователей (`?limit=100&offset=0`)  | 200                |
| `GET`    | `/users/{id}` | один пользователь                             | 200, 404           |
| `POST`   | `/users`      | создать пользователя                          | 201, 409, 422      |
| `PUT`    | `/users/{id}` | обновить переданные поля                      | 200, 404, 409, 422 |
| `DELETE` | `/users/{id}` | удалить                                       | 204, 404           |

Пользователь: `id`, `name`, `email` (уникальный, формат проверяется), `role` (`admin` или `user`), `created_at`.
Swagger UI с документацией и кнопкой «Try it out» доступен по адресу `http://localhost:8000/docs`.

Примеры:

```bash
curl localhost:8000/users
curl -X POST localhost:8000/users -H 'Content-Type: application/json' \
     -d '{"name":"Eve","email":"eve@example.com"}'
curl -X PUT localhost:8000/users/5 -H 'Content-Type: application/json' -d '{"role":"admin"}'
curl -X DELETE localhost:8000/users/5
```

## Локальный запуск

```bash
# В Docker
docker compose up -d --build        # http://localhost:8000/docs

# Без Docker
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest                              # тесты
uvicorn app.main:app --reload       # запуск; база создаётся в ./data/users.db
```

## Multi-stage сборка (Dockerfile)

В одном Dockerfile описаны три стадии (`FROM ... AS имя`). Каждая стадия — отдельный промежуточный образ.
В финальный образ попадает только то, что из промежуточных стадий явно скопировано через `COPY --from=`.

```
 builder ──────────────┬──> test     (линтер + тесты; сюда добавляются dev-зависимости)
 python:3.12-slim      │
 venv + зависимости    └──> runtime  (чистый python:3.12-slim + /opt/venv + app/)
                              └─ это и есть образ, который запускается
```

**1. `builder`** — установка зависимостей.
- Создаёт виртуальное окружение `/opt/venv` и ставит в него пакеты из `requirements.txt`.
- Сначала копируется только `requirements.txt`, а код — нет. Docker кэширует каждый слой, и
  если меняется только код, слой `pip install` берётся из кэша: пересборка занимает секунды.
- Здесь же могли бы стоять компиляторы (`gcc` и т.п.) для пакетов, которые собираются из исходников:
  в финальный образ они не попадут.

**2. `test`** — проверка внутри сборки (`FROM builder`).
- Добавляет pytest, ruff и httpx, копирует код и тесты и запускает `ruff check`, `ruff format --check`, `pytest`.
- Если хоть один тест упадёт, `docker build --target test .` завершится ошибкой.
- Эта стадия нужна для проверки «в той же среде, что и прод». Финальный образ от неё не зависит,
  поэтому при обычной сборке BuildKit её пропускает. В CI тесты идут отдельным джобом `test`.

**3. `runtime`** — финальный образ.
- Начинается с чистого `python:3.12-slim`, без следов pip, кэшей, тестов и dev-пакетов.
- `COPY --from=builder /opt/venv /opt/venv` берёт уже установленные зависимости, а `COPY app ./app` — только код.
- Запускается от непривилегированного пользователя `app`, а не от root: если сервис взломают,
  у атакующего внутри контейнера будет меньше прав.
- `VOLUME /data` — каталог базы, `EXPOSE 8000` — порт.
- `HEALTHCHECK` раз в 30 секунд обращается к `/health`, и Docker показывает статус `healthy`/`unhealthy`.
  По этому статусу деплой понимает, что новая версия поднялась.

Размеры для сравнения: образ стадии `test` весит около 215 МБ, финальный `runtime` — около 172 МБ.

```bash
docker build --target test .          # прогнать тесты внутри сборки
docker build -t users-api .           # собрать финальный образ (последняя стадия = runtime)
docker run -d -p 8000:8000 -v users-data:/data users-api
```

## Пайплайн GitLab CI (`.gitlab-ci.yml`)

GitLab ищет в корне репозитория файл `.gitlab-ci.yml` и при каждом пуше запускает описанный там пайплайн
на GitLab Runner. Пайплайн состоит из стадий. Стадии идут по очереди, и если джоб стадии упал,
следующие стадии не запускаются.

```
 push / MR
    │
    ▼
 ┌──────┐   ┌──────┐   ┌───────────────────────────┐   ┌─────────────────────────────┐
 │ lint │──>│ test │──>│ build                     │──>│ deploy (только main)        │
 │ ruff │   │pytest│   │ docker build + push       │   │ ssh на сервер: pull + run   │
 └──────┘   └──────┘   │ в GitLab Container Registry│   │ ждём статус healthy         │
                       └───────────────────────────┘   └─────────────────────────────┘
```

### `workflow: rules`
Пайплайн создаётся для Merge Request и для пушей в ветки. Если для ветки открыт MR, отдельный
branch-пайплайн не создаётся, чтобы один коммит не проверялся дважды.

### `lint`
Образ `python:3.12-slim`, ставит dev-зависимости и запускает `ruff check` (ошибки и стиль) и
`ruff format --check` (форматирование). Общая часть с `test` вынесена в скрытый шаблон `.python`
(подключается через `extends`). Там же настроен кэш pip: ключ кэша — хэш `requirements-dev.txt`,
поэтому пакеты не скачиваются заново, пока зависимости не изменятся.

### `test`
Запускает `pytest` и сохраняет отчёт `report.xml` в формате JUnit как артефакт
(`artifacts: reports: junit`). GitLab показывает результаты тестов во вкладке **Tests** пайплайна и в MR.
`when: always` сохраняет отчёт и при упавших тестах, чтобы было видно, что сломалось.

### `build`
- Образ `docker:27.5` и сервис `docker:27.5-dind` (Docker-in-Docker): внутри джоба поднимается свой Docker-демон,
  которому клиент отправляет команды сборки. `DOCKER_TLS_CERTDIR` включает TLS между клиентом и демоном.
- `docker login` в GitLab Container Registry. Переменные `CI_REGISTRY`, `CI_REGISTRY_USER`,
  `CI_REGISTRY_PASSWORD` GitLab выдаёт каждому джобу сам, настраивать их не нужно.
- `docker pull latest` + `--cache-from` + `BUILDKIT_INLINE_CACHE=1`: слои прошлого образа используются как кэш.
  На каждом раннере свежий dind без кэша, и без этого зависимости ставились бы при каждой сборке заново.
- `--target runtime` собирает финальную стадию. Метки OCI записывают в образ коммит и ссылку на проект.
- Образ публикуется с тегом `$CI_COMMIT_SHORT_SHA` (уникальный, неизменяемый: по нему видно,
  какой коммит задеплоен, и легко откатиться). На основной ветке он дополнительно тегается как `latest`.

### `deploy`
- Запускается только на основной ветке (`rules: if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH`).
- `environment: production` — в GitLab появляется окружение **Operate → Environments** с историей
  деплоев и кнопкой отката (Re-deploy предыдущего джоба).
- `resource_group: production` — два деплоя не пойдут одновременно, второй подождёт.
- Образ `alpine` + `openssh-client`. Ключ берётся из переменной `SSH_PRIVATE_KEY` типа File, `known_hosts`
  — из `SSH_KNOWN_HOSTS`. Если её нет, используется `ssh-keyscan`, но это менее безопасно.
- По SSH на сервере выполняется:
  1. `docker login` в registry: deploy token, если он есть, иначе `CI_JOB_TOKEN`
     (токен джоба действует, пока джоб идёт, этого хватает на pull);
  2. `docker pull` образа с тегом коммита;
  3. `docker rm -f` старого контейнера и `docker run` нового с `--restart unless-stopped`,
     пробросом порта `8000` и volume `users-data:/data` (данные сохраняются между деплоями);
  4. до 60 секунд ожидания статуса `healthy` от HEALTHCHECK. Если контейнер не поднялся, выводятся
     его логи и джоб падает: неудачный деплой сразу виден в пайплайне.

## Что настроить в GitLab

1. **Проект в GitLab.** Этот репозиторий размещён на GitHub. Чтобы пайплайн запускался, проект нужно
   импортировать в GitLab (*New project → Import project*) или подключить как
   *Run CI/CD for external repository* / настроить pull mirroring.
2. **Runner** с executor `docker` в режиме `privileged = true`: это нужно для Docker-in-Docker
   в джобе `build`. Shared runners на gitlab.com уже так настроены.
3. **Container Registry** включён в проекте (*Settings → General → Visibility → Container registry*).
4. **CI/CD Variables** (*Settings → CI/CD → Variables*):

   | Переменная        | Тип      | Значение                                                             |
   |-------------------|----------|----------------------------------------------------------------------|
   | `SSH_PRIVATE_KEY` | File     | приватный ключ для входа на сервер                                   |
   | `DEPLOY_HOST`     | Variable | IP или DNS-имя сервера                                               |
   | `DEPLOY_USER`     | Variable | пользователь на сервере                                              |
   | `SSH_KNOWN_HOSTS` | Variable | вывод `ssh-keyscan <DEPLOY_HOST>` (рекомендуется)                    |

   Чтобы сервер мог скачивать образ надёжнее, чем через токен джоба, создайте deploy token с именем
   `gitlab-deploy-token` и правом `read_registry` (*Settings → Repository → Deploy tokens*).
   GitLab сам подставит его в `CI_DEPLOY_USER`/`CI_DEPLOY_PASSWORD`.
5. **Сервер:** установлен Docker, пользователь `DEPLOY_USER` состоит в группе `docker`, публичный ключ
   добавлен в `~/.ssh/authorized_keys`, порт 8000 открыт.

После этого каждый пуш в `main` проходит цепочку lint → test → build → deploy, и сервис доступен по адресу
`http://<DEPLOY_HOST>:8000/docs`.
