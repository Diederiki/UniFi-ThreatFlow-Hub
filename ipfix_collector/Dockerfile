FROM python:3.12-slim
WORKDIR /app

# curl for the build-time MMDB download.
RUN apt-get update -qq && apt-get install -qq -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# GeoLite2-Country MMDB from a stable community mirror — used by the
# enrichment layer to populate destination_country on every flow row.
# ~6 MB, refreshed monthly. Falls back to no-enrichment if the download
# fails so the collector still boots.
RUN mkdir -p /app/data && \
    (curl -fsSL -o /app/data/GeoLite2-Country.mmdb \
        https://git.io/GeoLite2-Country.mmdb \
     || curl -fsSL -o /app/data/GeoLite2-Country.mmdb \
        https://raw.githubusercontent.com/P3TERX/GeoLite.mmdb/download/GeoLite2-Country.mmdb \
     || echo "geoip download failed; collector will run without country enrichment") \
    && ls -la /app/data/ || true

COPY app /app/app

ENV PYTHONUNBUFFERED=1 GEOIP_MMDB_PATH=/app/data/GeoLite2-Country.mmdb
CMD ["python", "-m", "app.main"]
