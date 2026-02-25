FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY scraper.py .

RUN PY=$(command -v python3 || command -v python) && \
    echo "* * * * * cd /app && ${PY} /app/scraper.py >> /var/log/scraper.log 2>&1" | crontab -

CMD ["sh", "-c", "printenv >> /etc/environment && cron && touch /var/log/scraper.log && tail -f /var/log/scraper.log"]
