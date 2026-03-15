FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    alsa-utils libasound2t64 libasound2-plugins \
    libpulse0 \
    dbus \
    && rm -rf /var/lib/apt/lists/* \
    && find /etc/alsa/conf.d/ -xtype l -delete 2>/dev/null || true

RUN curl -O http://ports.ubuntu.com/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_arm64.deb \
    && dpkg -i libssl1.1_1.1.1f-1ubuntu2_arm64.deb \
    && rm libssl1.1_1.1.1f-1ubuntu2_arm64.deb

# Use the full build with MPRIS/D-Bus support
RUN curl -L \
    https://github.com/Spotifyd/spotifyd/releases/download/v0.4.2/spotifyd-linux-aarch64-full.tar.gz \
    | tar xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/spotifyd

COPY contrib/asound.conf /etc/asound.conf

RUN cat > /usr/local/bin/start-spotifyd.sh <<'SCRIPT'
#!/bin/bash
set -e

if [ -S /host/run/dbus/system_bus_socket ]; then
    mkdir -p /run/dbus
    ln -sf /host/run/dbus/system_bus_socket /run/dbus/system_bus_socket
    echo "D-Bus socket linked"

    if dbus-send --system --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames >/dev/null 2>&1; then
        echo "D-Bus system bus is accessible"
    else
        echo "WARNING: Cannot communicate with D-Bus system bus"
    fi
else
    echo "WARNING: Host D-Bus socket not found at /host/run/dbus/system_bus_socket"
fi

SHARED_CONF="/etc/alsa-shared/asound.conf"
if [ -f "$SHARED_CONF" ] && [ -s "$SHARED_CONF" ]; then
    echo "Using shared ALSA config from backend..."
    cp "$SHARED_CONF" /etc/asound.conf
else
    echo "No shared ALSA config, detecting audio devices..."

    PLAYBACK_CARD=""
    PLAYBACK_CARD_ID=""
    PLAYBACK_TYPE=""

    while read -r line; do
        if echo "$line" | grep -qi "hdmi\|vc4"; then
            if [[ "$line" =~ ^card\ ([0-9]+):\ ([a-zA-Z0-9]+) ]]; then
                PLAYBACK_CARD="${BASH_REMATCH[1]}"
                PLAYBACK_CARD_ID="${BASH_REMATCH[2]}"
                PLAYBACK_TYPE="hdmi"
                echo "Found HDMI audio: card $PLAYBACK_CARD ($PLAYBACK_CARD_ID)"
                break
            fi
        fi
    done < <(aplay -l 2>/dev/null)

    if [ -z "$PLAYBACK_CARD" ]; then
        while read -r line; do
            line_lower=$(echo "$line" | tr '[:upper:]' '[:lower:]')
            if echo "$line_lower" | grep -q "wm8960\|hifiberry\|codec\|i2s\|pcm512\|tas5756\|allo\|iqaudio"; then
                if [[ "$line" =~ ^card\ ([0-9]+):\ ([a-zA-Z0-9]+) ]]; then
                    PLAYBACK_CARD="${BASH_REMATCH[1]}"
                    PLAYBACK_CARD_ID="${BASH_REMATCH[2]}"
                    PLAYBACK_TYPE="i2s"
                    echo "Found I2S codec: card $PLAYBACK_CARD ($PLAYBACK_CARD_ID)"
                    break
                fi
            fi
        done < <(aplay -l 2>/dev/null)
    fi

    MIC_CARD="0"
    while read -r line; do
        line_lower=$(echo "$line" | tr '[:upper:]' '[:lower:]')
        if echo "$line_lower" | grep -q "usb\|microphone\|mic\|wm8960"; then
            if [[ "$line" =~ card\ ([0-9]+): ]]; then
                MIC_CARD="${BASH_REMATCH[1]}"
                echo "Found microphone: card $MIC_CARD"
                break
            fi
        fi
    done < <(arecord -l 2>/dev/null)

    if [ "$PLAYBACK_TYPE" = "hdmi" ]; then
        echo "Configuring HDMI audio output with dmix + softvol..."
        cat > /etc/asound.conf <<ALSAEOF
pcm.hdmi_dmix {
    type dmix
    ipc_key 1024
    ipc_perm 0666
    slave {
        pcm "hw:$PLAYBACK_CARD,0"
        rate 48000
        period_size 1024
        buffer_size 4096
    }
}

pcm.hdmi_softvol {
    type softvol
    slave.pcm "hdmi_dmix"
    control {
        name "SoftMaster"
        card $PLAYBACK_CARD
    }
    min_dB -51.0
    max_dB 0.0
}

pcm.!default {
    type asym
    playback.pcm {
        type plug
        slave.pcm "hdmi_softvol"
    }
    capture.pcm {
        type plug
        slave.pcm "hw:$MIC_CARD,0"
    }
}

ctl.!default {
    type hw
    card $PLAYBACK_CARD
}
ALSAEOF
    elif [ -n "$PLAYBACK_CARD" ]; then
        echo "Configuring I2S codec audio output with dmix (card $PLAYBACK_CARD)..."
        cat > /etc/asound.conf <<ALSAEOF
pcm.dmixer {
    type dmix
    ipc_key 1024
    ipc_perm 0666
    slave {
        pcm "hw:$PLAYBACK_CARD,0"
        period_time 0
        period_size 1024
        buffer_size 4096
    }
}

pcm.!default {
    type asym
    playback.pcm {
        type plug
        slave.pcm "dmixer"
    }
    capture.pcm {
        type plug
        slave.pcm "hw:$MIC_CARD,0"
    }
}

ctl.!default {
    type hw
    card $PLAYBACK_CARD
}
ALSAEOF
    else
        echo "No recognized audio output, falling back to card 0 with dmix..."
        cat > /etc/asound.conf <<ALSAEOF
pcm.dmixer {
    type dmix
    ipc_key 1024
    ipc_perm 0666
    slave {
        pcm "hw:0,0"
        period_time 0
        period_size 1024
        buffer_size 4096
    }
}

pcm.!default {
    type plug
    slave.pcm "dmixer"
}

ctl.!default {
    type hw
    card 0
}
ALSAEOF
    fi
fi

echo "ALSA config:"
cat /etc/asound.conf

CRED_FILE="/root/.spotifyd/cache/oauth/credentials.json"
ZEROCONF_CRED="/root/.spotifyd/cache/zeroconf/credentials.json"
DISABLE_DISCOVERY="false"
if [ -f "$CRED_FILE" ] || [ -f "$ZEROCONF_CRED" ]; then
    DISABLE_DISCOVERY="true"
    echo "Cached credentials found, disabling zeroconf discovery"
else
    echo "No cached credentials, enabling zeroconf discovery for initial provisioning"
fi

mkdir -p /root/.config/spotifyd
cat > /root/.config/spotifyd/spotifyd.conf <<CONFEOF
[global]
backend = "alsa"
device_name = "GPT Home"
bitrate = 320
cache_path = "/root/.spotifyd/cache"
disable_discovery = $DISABLE_DISCOVERY
zeroconf_port = 1234
use_mpris = true
dbus_type = "system"
initial_volume = 90
volume_controller = "softvol"
autoplay = true
enable_volume_normalisation = false
device_type = "computer"
CONFEOF

echo "spotifyd.conf (disable_discovery=$DISABLE_DISCOVERY):"
cat /root/.config/spotifyd/spotifyd.conf

exec /usr/local/bin/spotifyd --no-daemon --verbose
SCRIPT
RUN chmod +x /usr/local/bin/start-spotifyd.sh

CMD ["/usr/local/bin/start-spotifyd.sh"]
