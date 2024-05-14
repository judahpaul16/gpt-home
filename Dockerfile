FROM ubuntu:23.04

# Set non-interactive installation to avoid tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install systemd
RUN apt-get update && apt-get install -y \
    systemd \
    systemd-sysv \
    libpam-systemd \
    dbus \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /lib/systemd/system/multi-user.target.wants/* \
    && rm -f /etc/systemd/system/*.wants/* \
    && rm -f /lib/systemd/system/local-fs.target.wants/* \
    && rm -f /lib/systemd/system/sockets.target.wants/*udev* \
    && rm -f /lib/systemd/system/sockets.target.wants/*initctl* \
    && rm -f /lib/systemd/system/sysinit.target.wants/systemd-tmpfiles-setup* \
    && rm -f /lib/systemd/system/systemd-update-utmp*

# Set up environment for systemd
ENV container docker

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates software-properties-common wget tar \
    systemd systemd-sysv libpam-systemd dbus

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
        nodejs && rm -rf /var/lib/apt/lists/*"

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

# Function to generate systemd service files
RUN generate_service() { \
    local name=$1; \
    local description=$2; \
    local exec_start=$3; \
    mkdir -p /etc/systemd/system/; \
    { \
        echo '[Unit]'; \
        echo "Description=${description}"; \
        echo 'After=network.target'; \
        echo '[Service]'; \
        echo "ExecStart=${exec_start}"; \
        echo 'Restart=always'; \
        echo '[Install]'; \
        echo 'WantedBy=multi-user.target'; \
    } > /etc/systemd/system/${name}.service; \
}; \
generate_service "jack" "JACK server" "/usr/local/bin/start_jack.sh"; \
generate_service "spotifyd" "Spotifyd service" "/usr/local/bin/spotifyd --no-daemon"; \
generate_service "gpt-home" "GPT Home service" "/bin/bash -c 'source /env/bin/activate && python /app/src/app.py'"; \
generate_service "web-interface" "Web Interface for GPT Home service" "/bin/bash -c 'source /env/bin/activate && cd src && uvicorn backend:app --host 0.0.0.0 --port 8000'";

# Enable services
RUN systemctl enable spotifyd.service gpt-home.service web-interface.service jack.service

# Create a startup script to start services when the container runs
RUN { \
    echo '#!/bin/bash'; \
    echo 'systemctl start spotifyd.service'; \
    echo 'systemctl start gpt-home.service'; \
    echo 'systemctl start web-interface.service'; \
    echo 'systemctl start jack.service'; \
    echo 'exec /bin/systemd'; \
} > /usr/local/bin/start_services.sh && \
    chmod +x /usr/local/bin/start_services.sh

# Expose the Uvicorn port
EXPOSE 8000

# Start systemd and the services
CMD ["/usr/local/bin/start_services.sh"]
