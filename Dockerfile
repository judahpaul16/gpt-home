FROM ubuntu:24.04

# Set non-interactive installation to avoid tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates software-properties-common tar

# Install ARMhf base libraries
RUN dpkg --add-architecture armhf

# Install necessary packages
RUN /bin/bash -c "yes | add-apt-repository universe && \
    dpkg --add-architecture armhf && apt-get update && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get install -y --no-install-recommends supervisor nano neovim \
        avahi-daemon avahi-utils libnss-mdns dbus iputils-ping \
        build-essential curl git libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
        libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev libraspberrypi-bin \
        libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev libjpeg-dev \
        portaudio19-dev alsa-utils libasound2-dev i2c-tools \
        python3.11 python3-pip python3.11-dev python3-smbus python3.11-venv \
        jackd2 libogg0 libflac-dev flac libespeak1 cmake openssl expect \
        nodejs libc6:armhf libdbus-1-3:armhf \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /var/cache/apt/archives/*"
        
# Ensure python3 points to Python 3.11
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --config python3 --force

# Download and setup spotifyd binary from GitHub release version v0.4.1
RUN curl -L https://github.com/Spotifyd/spotifyd/releases/download/v0.4.1/spotifyd-linux-aarch64-default.tar.gz -o spotifyd.tar.gz && \
    tar xzf spotifyd.tar.gz -C /usr/local/bin && chmod +x /usr/local/bin/spotifyd && \
    rm spotifyd.tar.gz

# Create Spotifyd configuration (this is just a basic config; adjust accordingly)
RUN mkdir -p /root/.config/spotifyd && { \
    echo '[global]'; \
    echo 'backend = "alsa" # Or pulseaudio if you use it'; \
    echo 'device_name = "GPT Home" # Name your device shows in Spotify Connect'; \
    echo 'bitrate = 320 # Choose bitrate from 96/160/320 kbps'; \
    echo 'cache_path = "/root/.spotifyd/cache"'; \
    echo 'disable_discovery = false'; \
    echo 'use_mpris = true'; \
    echo 'zeroconf_port = 1234'; \
} > /root/.config/spotifyd/spotifyd.conf

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# Prepare application directory
WORKDIR /app
COPY . /app

# Copy alarm sound to /usr/share/sounds
RUN mkdir -p /usr/share/sounds && cp /app/contrib/alarm.wav /usr/share/sounds

# Create virtual environment and install dependencies
RUN python3 -m venv /env && \
    /env/bin/pip install --no-cache-dir wheel && \
    /env/bin/pip install --no-cache-dir -r src/requirements.txt

# Start D-Bus system bus
RUN dbus-uuidgen > /var/lib/dbus/machine-id
RUN mkdir -p /var/run/dbus && dbus-daemon --system

# Set up Avahi
RUN sed -i 's/#allow-interfaces=eth0/allow-interfaces=eth0/' /etc/avahi/avahi-daemon.conf
RUN sed -i 's/#host-name=.*$/host-name=gpt-home/g' /etc/avahi/avahi-daemon.conf
RUN echo 'service dbus start && /usr/sbin/avahi-daemon --no-rlimits' > /usr/local/bin/start_avahi.sh && \
    chmod +x /usr/local/bin/start_avahi.sh

# Manage services with Supervisor
RUN mkdir -p /var/log/supervisor && \
    mkdir -p /etc/supervisor/conf.d && { \
    echo '[supervisord]'; \
    echo 'nodaemon=true'; \
    echo 'logfile=/dev/null'; \
    echo 'logfile_maxbytes=0'; \
    echo ''; \
    echo '[program:avahi]'; \
    echo 'command=/bin/bash /usr/local/bin/start_avahi.sh'; \
    echo 'stdout_logfile=/dev/fd/1'; \
    echo 'stdout_logfile_maxbytes=0'; \
    echo 'redirect_stderr=true'; \
    echo 'environment=HOME="/root",USER="root"'; \
    echo ''; \
    echo '[program:spotifyd]'; \
    echo 'command=/usr/local/bin/spotifyd --no-daemon'; \
    echo 'stdout_logfile=/var/log/spotifyd.log'; \
    echo 'stdout_logfile_maxbytes=1MB'; \
    echo 'redirect_stderr=true'; \
    echo ''; \
    echo '[program:app]'; \
    echo 'command=bash -c "source /env/bin/activate && cd src && python /app/src/app.py 2>/dev/null"'; \
    echo 'stdout_logfile=/dev/null'; \
    echo 'stdout_logfile_maxbytes=0'; \
    echo 'redirect_stderr=true'; \
    echo 'startsecs=0'; \
    echo 'autorestart=true'; \
    echo 'stopsignal=INT'; \
    echo 'stopasgroup=true'; \
    echo 'killasgroup=true'; \
    echo 'environment=HOME="/root",USER="root"'; \    
    echo ''; \
    echo '[program:web-interface]'; \
    echo 'command=bash -c "source /env/bin/activate && cd src && uvicorn backend:app --host 0.0.0.0 --port 8000"'; \
    echo 'stdout_logfile=/dev/fd/1'; \
    echo 'stdout_logfile_maxbytes=0'; \
    echo 'redirect_stderr=true'; \
} > /etc/supervisor/conf.d/supervisord.conf 

# Expose the Uvicorn port
EXPOSE 8000

# Start services with Supervisor
CMD ["/usr/bin/supervisord"]
