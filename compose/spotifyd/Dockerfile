FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies for spotifyd and avahi
RUN dpkg --add-architecture armhf && \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl tar \
    avahi-daemon avahi-utils libnss-mdns dbus \
    alsa-utils libasound2-dev \
    libc6:armhf libdbus-1-3:armhf \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Download and setup spotifyd binary
RUN curl -L --retry 5 --retry-delay 10 --connect-timeout 60 --max-time 300 \
    https://github.com/Spotifyd/spotifyd/releases/download/v0.4.1/spotifyd-linux-aarch64-default.tar.gz -o spotifyd.tar.gz && \
    tar xzf spotifyd.tar.gz -C /usr/local/bin && chmod +x /usr/local/bin/spotifyd && \
    rm spotifyd.tar.gz

# Create Spotifyd configuration
RUN mkdir -p /root/.config/spotifyd && { \
    echo '[global]'; \
    echo 'backend = "alsa"'; \
    echo 'device_name = "GPT Home"'; \
    echo 'bitrate = 320'; \
    echo 'cache_path = "/root/.spotifyd/cache"'; \
    echo 'disable_discovery = false'; \
    echo 'zeroconf_port = 1234'; \
    echo 'use_mpris = false'; \
} > /root/.config/spotifyd/spotifyd.conf

# Set up Avahi for mDNS
RUN sed -i 's/#host-name=.*$/host-name=gpt-home/g' /etc/avahi/avahi-daemon.conf && \
    dbus-uuidgen > /var/lib/dbus/machine-id

COPY compose/spotifyd/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Spotify Connect zeroconf port
EXPOSE 1234

CMD ["/entrypoint.sh"]
