FROM ubuntu:23.04

# Set non-interactive installation to avoid tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates software-properties-common wget tar 
    
# Install necessary packages
RUN /bin/bash -c "yes | add-apt-repository universe && \
    dpkg --add-architecture armhf && apt-get update && \
    apt-get install -y --no-install-recommends supervisor \
        avahi-daemon avahi-utils libnss-mdns dbus iputils-ping \
        build-essential curl git libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
        libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev \
        libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev libjpeg-dev \
        portaudio19-dev alsa-utils libasound2-dev i2c-tools \
        python3 python3-pip python3-dev python3-smbus python3-venv \
        jackd2 libogg0 libflac-dev flac libespeak1 cmake openssl expect \
        nodejs && rm -rf /var/lib/apt/lists/*"

# Setup JACK server
RUN { \
    echo 'if pgrep -x jackd > /dev/null; then'; \
    echo '  echo "JACK server already running. Terminating...'; \
    echo '  kill -9 $(pgrep -x jackd)'; \
    echo 'fi;'; \
    echo 'export JACK_NO_AUDIO_RESERVATION=1'; \
    echo '/usr/bin/jackd -r -d alsa -d hw:0 -r 44100 -p 1024 -n 3'; \
} > /usr/local/bin/start_jack.sh && \
    chmod +x /usr/local/bin/start_jack.sh

# Download and setup spotifyd binary from latest GitHub release
RUN wget https://github.com/Spotifyd/spotifyd/releases/latest/download/spotifyd-linux-armhf-full.tar.gz && \
    tar xzf spotifyd-linux-armhf-full.tar.gz -C /usr/local/bin && \
    rm spotifyd-linux-armhf-full.tar.gz

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

# Start D-Bus system bus
RUN dbus-uuidgen > /var/lib/dbus/machine-id
RUN mkdir -p /var/run/dbus && dbus-daemon --system

# Set up Avahi
RUN sed -i 's/#allow-interfaces=eth0/allow-interfaces=eth0/' /etc/avahi/avahi-daemon.conf
RUN sed -i 's/#host-name=.*$/host-name=gpt-home/g' /etc/avahi/avahi-daemon.conf

# Manage services with Supervisor
RUN mkdir -p /var/log/supervisor && \
    mkdir -p /etc/supervisor/conf.d && { \
    echo '[supervisord]'; \
    echo 'nodaemon=true'; \
    echo 'logfile=/dev/null'; \
    echo 'logfile_maxbytes=0'; \
    echo ''; \
    echo '[program:avahi]'; \
    echo 'command=/usr/sbin/avahi-daemon --no-rlimits'; \
    echo 'stdout_logfile=/dev/fd/1'; \
    echo 'stdout_logfile_maxbytes=0'; \
    echo 'redirect_stderr=true'; \
    echo ''; \
    echo '[program:jackd]'; \
    echo 'command=/usr/local/bin/start_jack.sh'; \
    echo 'stdout_logfile=/dev/fd/1'; \
    echo 'stdout_logfile_maxbytes=0'; \
    echo 'redirect_stderr=true'; \
    echo ''; \
    echo '[program:spotifyd]'; \
    echo 'command=/usr/local/bin/spotifyd --no-daemon'; \
    echo 'stdout_logfile=/var/log/spotifyd.log'; \
    echo 'stdout_logfile_maxbytes=1MB'; \
    echo 'redirect_stderr=true'; \
    echo ''; \
    echo '[program:app]'; \
    echo 'command=bash -c "source /env/bin/activate && python /app/src/app.py 2>/dev/null"'; \
    echo 'stdout_logfile=/dev/null'; \
    echo 'stdout_logfile_maxbytes=0'; \
    echo 'redirect_stderr=true'; \
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
