# Microsoft's Playwright image already has Chromium + system deps installed
# at the version Playwright expects, so we don't have to manage browser
# installation ourselves.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Xvfb so we can run Chromium with a virtual display. Headless Chromium's
# WebRTC stack fails ICE host lookups in some Linux/Docker combos that
# headed-Chromium-on-Xvfb sails through. Net cost is ~50MB image + a
# few hundred MB RSS at runtime — acceptable for our scale.
USER root
RUN apt-get update -qq && apt-get install -qq -y --no-install-recommends \
        xvfb \
        dnsutils iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY app /app/app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# The Chrome profile dir is the only persistent state. Mounted from a
# docker volume so cookies survive restarts.
RUN mkdir -p /var/lib/streamer && chown -R pwuser:pwuser /var/lib/streamer

USER pwuser
ENV PYTHONUNBUFFERED=1 DISPLAY=:99

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
