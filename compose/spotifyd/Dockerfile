FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    alsa-utils libasound2t64 libasound2-plugins \
    libpulse0 dbus \
    && rm -rf /var/lib/apt/lists/*

RUN curl -L \
    https://github.com/Spotifyd/spotifyd/releases/download/v0.4.1/spotifyd-linux-aarch64-default.tar.gz \
    | tar xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/spotifyd

RUN mkdir -p /root/.config/spotifyd && cat > /root/.config/spotifyd/spotifyd.conf <<EOF
[global]
backend = "alsa"
device_name = "GPT Home"
bitrate = 320
cache_path = "/root/.spotifyd/cache"
disable_discovery = false
zeroconf_port = 1234
use_mpris = true
dbus_type = "system"
initial_volume = 90
volume_controller = "softvol"
autoplay = true
enable_volume_normalisation = false
EOF

CMD ["/usr/local/bin/spotifyd", "--no-daemon", "--verbose"]
