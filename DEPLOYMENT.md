# Visions — деплой и откат

## Перед деплоем
1. Сменить пароль приложения Gmail (старый остался в истории git).
2. Резервная копия: `cp db.sqlite3 db.sqlite3.bak-$(date +%F)` и архив `media/`.
3. Python на сервере ≥ 3.11 (Pillow 13). Docker-образ собирается на `python:3.12`.
4. Создать `.env` по образцу `.env.example`. Обязательно: `SECRET_KEY`, `DEBUG=False`,
   `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `TASK_NOTIFY_EMAILS`.
   За nginx: `USE_X_FORWARDED_PROTO=True`, `TRUST_X_FORWARDED_FOR=True`.
   `SECURE_SSL_REDIRECT=True` — только если nginx передаёт `X-Forwarded-Proto`, иначе будет бесконечный редирект.

## Деплой
```bash
pip install -r requirements.txt
python manage.py check --deploy
python manage.py migrate            # одна миграция 0013: добавляет Task.points_awarded
python manage.py collectstatic --noinput   # обязательно: иначе нет нового CSS/JS
sudo systemctl restart gunicorn      # или docker compose up -d --build
```

## nginx
```nginx
location /static/ { alias /app/static/; expires 7d; }
location /media/profile_images/ { alias /app/media/profile_images/; }
location /media/ { return 404; }               # задания и ответы студентов — только через Django
location /protected-media/ { internal; alias /app/media/; }   # если PROTECTED_MEDIA_ACCEL_PREFIX=/protected-media/
location = /login/       { limit_req zone=login burst=5 nodelay; proxy_pass http://app; include proxy_params; }
location = /admin/login/ { limit_req zone=login burst=5 nodelay; proxy_pass http://app; include proxy_params; }
location / {
    proxy_pass http://app;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    client_max_body_size 25m;
}
# в блоке http: limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;
```
Без nginx: `SERVE_FILES_WITH_DJANGO=True` (Django сам отдаёт /static/ и аватары, приватные файлы — всё равно закрыты).

## Проверка после деплоя
- Вход по логину и по email; неверный пароль 6 раз → «Слишком много попыток».
- Студент: скачать задание, отправить ответ (PDF), получить письмо ментору.
- `https://<домен>/media/tasks/<любой файл>` → 404; кнопка «Скачать задание» работает.
- Ментор: «Задания» → студент → «Скачать файл».
- Стили загружены (иначе не выполнен `collectstatic`).

## Откат
Миграция 0013 только добавляет колонку и обратима; существующие данные не меняются.

1. **Остановить приложение**, чтобы во время отката не было записей в БД:
   `sudo systemctl stop gunicorn` (или `docker compose stop web`). Nginx может показывать страницу обслуживания.
2. **Сохранить текущее состояние** (даже если есть бэкап до деплоя — в нём нет данных, внесённых после):
   `sqlite3 db.sqlite3 ".backup 'db.sqlite3.before-rollback-$(date +%F-%H%M)'"` и архив `media/`.
   Права на копии: `chmod 600` — в них хеши паролей и персональные данные; не класть в git и в публичные каталоги.
3. **Откатить схему на новом коде**: `python manage.py migrate django_app 0012`
   (удаляет только колонку `points_awarded`; задания, баллы и уведомления остаются).
4. **Вернуть предыдущую версию кода**: `git checkout <предыдущий-коммит>`, `pip install -r requirements.txt`.
5. **Секреты**: старый `settings.py` содержит пароль SMTP в коде — **не вписывать в него новый пароль**
   и не коммитить. Временно экспортировать его через переменную окружения на сервере невозможно
   (старый код её не читает), поэтому при откате отправка писем может не работать — это допустимо
   на время аварии. `.env` не удалять: он понадобится при повторном деплое. `chmod 600 .env`.
6. **Запустить приложение** и пройти проверки из раздела «Проверка после деплоя».
7. Если шаг 3 пропущен — старый код всё равно работает (у колонки DEFAULT 0 в БД).
8. Крайний случай (повреждение данных): остановить приложение и восстановить копию из шага 2
   или бэкап до деплоя; данные, внесённые после копии, будут потеряны.

Повторный деплой после отката: `migrate` снова пометит уже одобренные задания, повторного начисления баллов не будет.

Риски: SQLite работает в режиме IMMEDIATE-транзакций (OPTIONS в settings) — запись сериализуется,
параллельные запросы ждут до 20 с вместо ошибки «database is locked». Файловый кеш блокировок (`CACHE_DIR`) должен быть доступен на запись всем воркерам;
блокировка по логину позволяет постороннему на 15 минут запереть аккаунт (можно ослабить `LOGIN_FAILURE_LIMIT`).
