FROM ubuntu:23.04

# Set non-interactive installation to avoid tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install CA certificates first to handle SSL/TLS downloads properly
RUN apt-get update && apt-get install -y ca-certificates software-properties-common wget tar

# Install necessary packages
RUN /bin/bash -c "yes | add-apt-repository universe && \
    dpkg --add-architecture armhf && apt-get update && \
    apt-get install -y --no-install-recommends \
        avahi-daemon avahi-utils libnss-mdns dbus iputils-ping \
        build-essential curl git libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
        libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev \
        libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev libjpeg-dev \
        portaudio19-dev alsa-utils libasound2-dev i2c-tools \
        python3 python3-pip python3-dev python3-smbus python3-venv \
        jackd2 libogg0 libflac-dev flac libespeak1 cmake openssl expect \
        nodejs supervisor && rm -rf /var/lib/apt/lists/*"

# Add ALSA configuration
RUN echo 'pcm.!default { type hw card 0 }' > /etc/asound.conf && \
    echo 'ctl.!default { type hw card 0 }' >> /etc/asound.conf

# Start with JACK server
RUN echo '/usr/bin/jackd -r -d alsa -d hw:0 -r 44100 -p 1024 -n 3' > /usr/local/bin/start_jack.sh && \
    chmod +x /usr/local/bin/start_jack.sh

# Download and setup spotifyd binary from latest GitHub release
RUN wget https://github.com/Spotifyd/spotifyd/releases/latest/download/spotifyd-linux-armhf-default.tar.gz && \
    tar xzf spotifyd-linux-armhf-default.tar.gz -C /usr/local/bin && \
    rm spotifyd-linux-armhf-default.tar.gz

# Create Spotifyd configuration (this is just a basic config; adjust accordingly)
RUN mkdir -p /root/.config/spotifyd && { \
    echo '[global]'; \
    echo 'backend = "alsa" # Or pulseaudio if you use it'; \
    echo 'device_name = "GPT Home" # Name your device shows in Spotify Connect'; \
    echo 'bitrate = 320 # Choose bitrate from 96/160/320 kbps'; \
    echo 'cache_path = "/root/.spotifyd/cache"'; \
    echo 'discovery = false'; \
} > /root/.config/spotifyd/spotifyd.conf

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# Prepare application directory
WORKDIR /app
COPY . /app

# Create virtual environment and install dependencies
RUN python3 -m venv /env && \
    /env/bin/pip install --no-cache-dir --use-pep517 -r src/requirements.txt

# Setup Avahi for mDNS (https://gpt-home.local)
RUN sed -i 's/#host-name=.*$/host-name=gpt-home/g' /etc/avahi/avahi-daemon.conf && \
    dbus-uuidgen > /var/lib/dbus/machine-id && \
    mkdir -p /var/run/dbus && \
    dbus-daemon --system --fork && \
    avahi-daemon --no-drop-root --daemonize --debug

# Supervisord configuration
RUN { \
    echo '[supervisord]'; \
    echo 'nodaemon=true'; \
    echo '[program:spotifyd]'; \
    echo 'command=/usr/local/bin/spotifyd --no-daemon'; \
    echo '[program:gpt-home]'; \
    echo 'command=/bin/bash -c "source /env/bin/activate && python /app/src/app.py"'; \
    echo '[program:web-interface]'; \
    echo 'command=/bin/bash -c "source /env/bin/activate && cd /app/src && uvicorn backend:app --host 0.0.0.0 --port 8000"'; \
    echo '[program:jack]'; \
    echo 'command=/usr/local/bin/start_jack.sh'; \
} > /etc/supervisor/conf.d/supervisord.conf

# Expose the Uvicorn port
EXPOSE 8000

# Start all processes
ENTRYPOINT ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
