FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    alsa-utils libasound2t64 libasound2-plugins \
    libpulse0 \
    dbus \
    && rm -rf /var/lib/apt/lists/*

RUN curl -O http://ports.ubuntu.com/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_arm64.deb \
    && dpkg -i libssl1.1_1.1.1f-1ubuntu2_arm64.deb \
    && rm libssl1.1_1.1.1f-1ubuntu2_arm64.deb

# Use the full build with MPRIS/D-Bus support
RUN curl -L \
    https://github.com/Spotifyd/spotifyd/releases/download/v0.4.2/spotifyd-linux-aarch64-full.tar.gz \
    | tar xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/spotifyd

# Copy ALSA configuration
COPY contrib/asound.conf /etc/asound.conf

# spotifyd config: MPRIS enabled for D-Bus control
# Uses default ALSA device (configured via asound.conf)
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
device_type = "computer"
EOF

# Entrypoint script to set up D-Bus symlink, ALSA config, and start spotifyd
RUN cat > /usr/local/bin/start-spotifyd.sh <<'EOF'
#!/bin/bash
set -e

# Create symlink so spotifyd can find the host D-Bus socket at the standard path
if [ -S /host/run/dbus/system_bus_socket ]; then
    mkdir -p /run/dbus
    ln -sf /host/run/dbus/system_bus_socket /run/dbus/system_bus_socket
    echo "D-Bus socket linked: /run/dbus/system_bus_socket -> /host/run/dbus/system_bus_socket"

    # Test D-Bus connectivity
    if dbus-send --system --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames >/dev/null 2>&1; then
        echo "D-Bus system bus is accessible"
    else
        echo "WARNING: Cannot communicate with D-Bus system bus"
    fi
else
    echo "WARNING: Host D-Bus socket not found at /host/run/dbus/system_bus_socket"
fi

# Detect HDMI audio and generate ALSA config (same logic as backend)
echo "Detecting audio devices..."

# Find HDMI audio device
HDMI_CARD=""
HDMI_CARD_ID=""
while read -r line; do
    if echo "$line" | grep -qi "hdmi\|vc4"; then
        # Extract card number and ID: "card 2: vc4hdmi0 [vc4-hdmi-0], device 0: ..."
        if [[ "$line" =~ ^card\ ([0-9]+):\ ([a-zA-Z0-9]+) ]]; then
            HDMI_CARD="${BASH_REMATCH[1]}"
            HDMI_CARD_ID="${BASH_REMATCH[2]}"
            echo "Found HDMI audio: card $HDMI_CARD ($HDMI_CARD_ID)"
            break
        fi
    fi
done < <(aplay -l 2>/dev/null)

# Find microphone card
MIC_CARD="0"
while read -r line; do
    line_lower=$(echo "$line" | tr '[:upper:]' '[:lower:]')
    if echo "$line_lower" | grep -q "usb\|microphone\|mic"; then
        if [[ "$line" =~ card\ ([0-9]+): ]]; then
            MIC_CARD="${BASH_REMATCH[1]}"
            echo "Found microphone: card $MIC_CARD"
            break
        fi
    fi
done < <(arecord -l 2>/dev/null)

# Generate ALSA config
if [ -n "$HDMI_CARD" ] && [ -n "$HDMI_CARD_ID" ]; then
    echo "Configuring HDMI audio output with softvol..."
    cat > /etc/asound.conf <<ALSAEOF
# HDMI playback with software volume control (auto-detected)
# Uses hdmi:CARD=$HDMI_CARD_ID which handles IEC958 format conversion

pcm.hdmi_converted {
    type plug
    slave.pcm "hdmi:CARD=$HDMI_CARD_ID,DEV=0"
}

pcm.hdmi_softvol {
    type softvol
    slave.pcm "hdmi_converted"
    control {
        name "SoftMaster"
        card $HDMI_CARD
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
    card $HDMI_CARD
}
ALSAEOF
    echo "ALSA config generated:"
    cat /etc/asound.conf
else
    echo "No HDMI audio found, configuring card 0 for playback..."
    cat > /etc/asound.conf <<ALSAEOF
pcm.!default {
    type plug
    slave.pcm "hw:0,0"
}

ctl.!default {
    type hw
    card 0
}
ALSAEOF
    cat /etc/asound.conf
fi

exec /usr/local/bin/spotifyd --no-daemon --verbose
EOF
RUN chmod +x /usr/local/bin/start-spotifyd.sh

CMD ["/usr/local/bin/start-spotifyd.sh"]
