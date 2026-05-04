# Microsoft's Playwright image already has Chromium + system deps installed
# at the version Playwright expects, so we don't have to manage browser
# installation ourselves.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

# The Chrome profile dir is the only persistent state. Mounted from a
# docker volume so cookies survive restarts.
RUN mkdir -p /var/lib/streamer && chown -R pwuser:pwuser /var/lib/streamer

# Run as the non-root pwuser the playwright image already provides.
USER pwuser
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
