FROM ubuntu:23.04

# Set non-interactive installation to avoid tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install CA certificates first to handle SSL/TLS downloads properly
RUN apt-get update && apt-get install -y ca-certificates software-properties-common wget tar

# Install necessary packages
RUN /bin/bash -c "yes | add-apt-repository universe && \
    dpkg --add-architecture armhf && apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential curl git libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
        libsqlite3-dev llvm libncursesw5-dev xz-utils tk-dev \
        libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev libjpeg-dev \
        portaudio19-dev alsa-utils libasound2-dev i2c-tools \
        python3 python3-pip python3-dev python3-smbus python3-venv \
        jackd2 libogg0 libflac-dev flac libespeak1 cmake openssl expect \
        nodejs supervisor && rm -rf /var/lib/apt/lists/*"

# Download and setup spotifyd binary from latest GitHub release
RUN wget https://github.com/Spotifyd/spotifyd/releases/latest/download/spotifyd-linux-armhf-default.tar.gz && \
    tar xzf spotifyd-linux-armhf-default.tar.gz -C /usr/local/bin && \
    rm spotifyd-linux-armhf-default.tar.gz

# Create Spotifyd configuration (this is just a basic config; adjust accordingly)
RUN mkdir -p /root/.config/spotifyd && \
    echo "[global]" \
    "\nbackend = \"alsa\" # Or pulseaudio if you use it" \
    "\ndevice_name = \"GPT Home\" # Name your device shows in Spotify Connect" \
    "\nbitrate = 320 # Choose bitrate from 96/160/320 kbps" \
    "\ncache_path = \"/root/.spotifyd/cache\"" \
    "\ndiscovery = false" > /root/.config/spotifyd/spotifyd.conf

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# Prepare application directory
WORKDIR /app
COPY . /app

# Create a virtual environment
RUN python3 -m venv env
RUN . env/bin/activate

# Install Python and Node dependencies
RUN pip install --no-cache-dir --break-system-packages -r src/requirements.txt && \
    npm install

# Supervisord configuration
RUN echo "[supervisord]\nnodaemon=true\n" \
    "[program:spotifyd]\ncommand=spotifyd --no-daemon\n" \
    "[program:gpt-home]\ncommand=python src/app.py\n" \
    "[program:web-interface]\ncommand=uvicorn backend:app --host 0.0.0.0 --port 8000\n" > /etc/supervisor/conf.d/supervisord.conf

# Expose the Uvicorn port
EXPOSE 8000

# Start all processes
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
