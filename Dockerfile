FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей, нужных для Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем сам браузер Chromium для Playwright внутри контейнера
RUN playwright install chromium
RUN playwright install-deps chromium

# Копируем весь остальной код проекта
COPY . .

# Команда запуска бота
CMD ["python", "main.py"]
