FROM python:3.12-slim-bookworm
ARG BUILD_ARCH
LABEL io.hass.name="Watchlists" io.hass.type="addon" io.hass.version="0.2.0" io.hass.arch="${BUILD_ARCH}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DISPLAY=:99 \
    CHROMIUM_PATH=/usr/bin/chromium WATCHLIST_DATA=/data/watchlists
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium xvfb gosu ca-certificates fonts-noto-core fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin watchlists \
    && chmod 755 /app/run.sh \
    && pip install --no-cache-dir -r requirements.txt
EXPOSE 8099
ENTRYPOINT ["/app/run.sh"]
