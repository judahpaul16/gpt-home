FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install base tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates software-properties-common \
    && yes | add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    bash build-essential curl git libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev \
    libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev libjpeg-dev \
    portaudio19-dev alsa-utils libasound2-dev i2c-tools \
    python3.11 python3-pip python3.11-dev python3-smbus python3.11-venv \
    jackd2 libogg0 libflac-dev flac libespeak1 cmake openssl \
    libpq-dev postgresql-client nano libraspberrypi-bin docker.io \
    ffmpeg \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libdrm-dev libgbm-dev libinput-dev libudev-dev \
    libgl1-mesa-dev libgles2-mesa-dev mesa-utils \
    fonts-noto-cjk fonts-dejavu \
    dbus libdbus-1-dev libdbus-glib-1-dev pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Ensure python3 points to Python 3.11
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app
COPY src/requirements.txt /app/src/requirements.txt

# Create virtual environment and install dependencies
# Use CFLAGS=-O0 to reduce memory usage during compilation (critical for Raspberry Pi)
# Use --default-timeout=1000 to handle slow PyPI connections on limited bandwidth networks
RUN python3 -m venv /env && \
    /env/bin/pip install --no-cache-dir --default-timeout=1000 --retries 5 --upgrade pip wheel setuptools && \
    MAKEFLAGS="-j1" CFLAGS="-O0" /env/bin/pip install --no-cache-dir --default-timeout=1000 --retries 5 -r src/requirements.txt

COPY src /app/src
COPY contrib/alarm.wav /usr/share/sounds/alarm.wav
COPY contrib/asound.conf /etc/asound.conf
COPY src/display/font5x8.bin /app/font5x8.bin

RUN mkdir -p /app/logs
RUN touch /app/logs/events.log

ENV PATH="/env/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYGAME_HIDE_SUPPORT_PROMPT=1

EXPOSE 8000

# Entrypoint script to set up D-Bus symlink, ALSA config, and start backend
RUN cat > /usr/local/bin/start-backend.sh <<'EOF'
#!/bin/bash
set -e

# Create symlink so dbus-python can find the host D-Bus socket at the standard path
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

# Run uvicorn which starts both FastAPI backend and voice assistant in same process
CMD ["/usr/local/bin/start-backend.sh"]
