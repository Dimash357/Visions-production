# Используем официальный образ Python
FROM python:3.12

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файлы проекта в контейнер
COPY . /app/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Открываем порт
EXPOSE 8000

# Запуск Gunicorn
CMD ["gunicorn", "--workers=3", "--timeout=60", "--bind", "0.0.0.0:8000", "django_settings.wsgi:application"]

