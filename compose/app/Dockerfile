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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Ensure python3 points to Python 3.11
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app
COPY src/requirements.txt /app/src/requirements.txt

# Create virtual environment and install dependencies
RUN python3 -m venv /env && \
    /env/bin/pip install --no-cache-dir wheel && \
    /env/bin/pip install --no-cache-dir pygame-ce --upgrade && \
    /env/bin/pip install --no-cache-dir -r src/requirements.txt

COPY src /app/src
COPY logs /app/logs
COPY contrib/alarm.wav /usr/share/sounds/alarm.wav
COPY src/display/font5x8.bin /app/font5x8.bin

ENV PATH="/env/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYGAME_HIDE_SUPPORT_PROMPT=1

EXPOSE 8000

# Run uvicorn which starts both FastAPI backend and voice assistant in same process
CMD ["uvicorn", "src.backend:app", "--host", "0.0.0.0", "--port", "8000"]
