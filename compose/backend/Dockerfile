FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates software-properties-common \
    && yes | add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    bash build-essential curl git libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev \
    libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev libjpeg-dev \
    portaudio19-dev libasound2-dev \
    python3.11 python3-pip python3.11-dev python3.11-venv \
    jackd2 libflac-dev cmake libespeak1 \
    libpq-dev libgpiod-dev \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libdrm-dev libgbm-dev libinput-dev libudev-dev \
    libgl1-mesa-dev libgles2-mesa-dev \
    libdbus-1-dev libdbus-glib-1-dev pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app
COPY src/requirements.txt /app/src/requirements.txt

# CFLAGS=-O0 reduces memory usage during compilation
# --default-timeout=1000 handles slow PyPI connections on limited bandwidth networks
RUN python3 -m venv /env && \
    /env/bin/pip install --no-cache-dir --default-timeout=1000 --retries 5 --upgrade pip wheel setuptools && \
    MAKEFLAGS="-j1" CFLAGS="-O0" /env/bin/pip install --no-cache-dir --default-timeout=1000 --retries 5 -r src/requirements.txt

# --- Runtime stage ---
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates software-properties-common \
    && yes | add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv \
    libportaudio2 alsa-utils libasound2-plugins i2c-tools \
    jackd2 libogg0 flac libespeak1 openssl \
    libpq5 postgresql-client libgpiod2 \
    ffmpeg \
    libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0 \
    libdrm2 libgbm1 libinput10 \
    libgl1-mesa-dri libgles2 \
    fonts-noto-cjk fonts-dejavu \
    dbus libdbus-1-3 libdbus-glib-1-2 \
    libxml2 libxslt1.1 libffi8 libjpeg-turbo8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

COPY --from=builder /env /env

WORKDIR /app
COPY src /app/src
COPY contrib/alarm.wav /usr/share/sounds/alarm.wav
COPY contrib/asound.conf /etc/asound.conf
RUN mkdir -p /app/logs && touch /app/logs/events.log

ENV PATH="/env/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYGAME_HIDE_SUPPORT_PROMPT=1

EXPOSE 8000

RUN cat > /usr/local/bin/start-backend.sh <<'EOF'
#!/bin/bash
set -e

if [ -S /host/run/dbus/system_bus_socket ]; then
    mkdir -p /run/dbus
    ln -sf /host/run/dbus/system_bus_socket /run/dbus/system_bus_socket
    echo "D-Bus socket linked: /run/dbus/system_bus_socket -> /host/run/dbus/system_bus_socket"
else
    echo "WARNING: Host D-Bus socket not found at /host/run/dbus/system_bus_socket"
fi

exec uvicorn src.backend:app --host 127.0.0.1 --port 8000
EOF
RUN chmod +x /usr/local/bin/start-backend.sh

CMD ["/usr/local/bin/start-backend.sh"]
