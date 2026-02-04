#!/bin/bash

latest_release=$(curl -s https://api.github.com/repos/judahpaul16/gpt-home/releases/latest | grep 'tag_name' | cut -d\" -f4)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[0;37m'
NC='\033[0m' # No Color

echo ""
echo -e "${MAGENTA}"
echo "GPT Home $latest_release"
echo "Created by Judah Paul"
echo "More info @ https://github.com/judahpaul16/gpt-home/"
echo -e "${NC}"

echo -e "${GREEN}"
echo "  ____ ____ _____   _   _                      "
echo " / ___|  _ \\_   _| | | | | ___  _ __ ___   ___ "
echo "| |  _| |_) || |   | |_| |/ _ \\| '_ \` _ \\ / _ \\"
echo "| |_| |  __/ | |   |  _  | (_) | | | | | |  __/"
echo " \\____|_|    |_|   |_| |_|\\___/|_| |_| |_|\\___|"
echo -e "${NC}"

echo -e "${CYAN}"
echo "         ______________"
echo "        | how may I    |"
echo "        | assist you   |"
echo "        | today?       |"
echo "        |______________|"
echo "                 \\                       |"
echo "                  \\                      |"
echo "                   \\                     |"
echo "   _______                   ________    |"
echo "  |ooooooo|      ____       | __  __ |   |"
echo "  |[]+++[]|     [____]      |/  \\/  \\|   |"
echo "  |+ ___ +|     ]()()[      |\\__/\\__/|   |"
echo "  |:|   |:|   ___\\__/___    |[][][][]|   |"
echo "  |:|___|:|  |__|    |__|   |++++++++|   |"
echo "  |[]===[]|   |_|/  \\|_|    | ______ |   |"
echo "_ ||||||||| _ | | __ | | __ ||______|| __|"
echo "  |_______|   |_|[::]|_|    |________|   \\"
echo "              \\_|_||_|_/                  \\"
echo "                |_||_|                     \\"
echo "               _|_||_|_                     \\"
echo "      ____    |___||___|                     \\"
echo -e "${NC}"

# Mask systemd-networkd-wait-online.service to prevent boot delays
sudo systemctl mask systemd-networkd-wait-online.service

# Set Permissions
sudo chown -R $(whoami):$(whoami) .
sudo chmod -R 755 .

# Disable unattended-upgrades to prevent package lock issues during setup
if systemctl is-active --quiet unattended-upgrades 2>/dev/null; then
    echo "Stopping unattended-upgrades to prevent package lock..."
    sudo systemctl stop unattended-upgrades
    sudo systemctl disable unattended-upgrades
fi

# Wait for any existing package manager lock to be released
if command -v apt-get >/dev/null; then
    while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
        echo -n "."
        sleep 1
    done
fi

# Function to install system dependencies
function install() {
    local package=$1
    echo "Ensuring package '$package' is installed..."

    # Detect the package management system
    if command -v apt-get >/dev/null; then
        if [ "$package" == "docker" ]; then
            # Install Docker from official Docker repository (includes buildx plugin)
            if dpkg -s docker-ce docker-buildx-plugin docker-compose-plugin &>/dev/null; then
                echo "Docker with buildx already installed"
            else
                echo "Installing Docker from official repository (includes buildx)..."
                # Remove old docker.io if present
                sudo apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc 2>/dev/null || true
                # Add Docker's official GPG key and repository
                sudo apt-get update
                sudo apt-get install -y ca-certificates curl
                sudo install -m 0755 -d /etc/apt/keyrings
                sudo curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg -o /etc/apt/keyrings/docker.asc
                sudo chmod a+r /etc/apt/keyrings/docker.asc
                # Add the repository
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
                sudo apt-get update
                if ! sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
                    echo -e "${RED}ERROR: Failed to install Docker from official repository${NC}"
                    exit 1
                fi
            fi
        elif ! dpkg -s "$package" >/dev/null 2>&1; then
            sudo yes | add-apt-repository universe >/dev/null 2>&1 || true
            sudo apt update || true
            if ! sudo apt-get install -y "$package"; then
                echo -e "${RED}ERROR: Failed to install $package${NC}"
                exit 1
            fi
        fi
    elif command -v yum >/dev/null; then
        if ! rpm -q "$package" >/dev/null 2>&1; then
            sudo yum install -y epel-release >/dev/null 2>&1 || true
            sudo yum makecache --timer || true
            sudo yum install -y "$package"
        fi
    elif command -v dnf >/dev/null; then
        if ! dnf list installed "$package" >/dev/null 2>&1; then
            sudo dnf install -y epel-release >/dev/null 2>&1 || true
            sudo dnf makecache --timer || true
            sudo dnf install -y "$package"
        fi
    elif command -v zypper >/dev/null; then
        if ! zypper se -i "$package" >/dev/null 2>&1; then
            sudo zypper refresh || true
            sudo zypper install -y "$package"
        fi
    elif command -v pacman >/dev/null; then
        if ! pacman -Q "$package" >/dev/null 2>&1; then
            sudo pacman -Sy
            sudo pacman -S --noconfirm "$package"
        fi
    else
        echo "Package manager not supported."
        return 1
    fi

    if [ "$package" == "docker" ]; then
        # Verify docker group exists
        if ! getent group docker >/dev/null 2>&1; then
            echo -e "${RED}ERROR: Docker installation failed - 'docker' group does not exist.${NC}"
            echo -e "${YELLOW}This usually means the package manager was locked during installation.${NC}"
            echo -e "${YELLOW}Please run: sudo apt-get install -y docker-ce${NC}"
            echo -e "${YELLOW}Then re-run this script.${NC}"
            exit 1
        fi

        # Check if user is in docker group (check actual group membership, not just current session)
        if ! id -nG "$(whoami)" | grep -qw docker; then
            echo "Adding $(whoami) to the 'docker' group..."
            sudo usermod -aG docker $(whoami)
            echo -e "${RED}User added to 'docker' group but the session must be reloaded to access the Docker daemon.${NC}"
            echo -e "${YELLOW}Please log out, log back in, and re-run this script.${NC}"
            exit 0
        fi

        # Ensure Docker daemon is running
        if ! systemctl is-active --quiet docker; then
            echo "Starting Docker daemon..."
            sudo systemctl start docker
        fi
    fi
}

install chrony
install docker
install alsa-utils
install libdrm2
install libgbm1
install mesa-utils
sudo systemctl enable docker
sudo systemctl start docker

# Create ALSA config (asound.conf, adjust as needed)
sudo tee /etc/asound.conf > /dev/null <<EOF
pcm.!default { type hw card Headphones device 0 }
ctl.!default { type hw card Headphones }
EOF

# Set System dbus policy for spotifyd MPRIS control
# Use /etc/dbus-1/system.d/ for local configuration (not /usr/share which is for packages)
# Note: spotifyd registers as org.mpris.MediaPlayer2.spotifyd.instance1 (with instance suffix)
sudo tee /etc/dbus-1/system.d/spotifyd.conf > /dev/null <<EOF
<!DOCTYPE busconfig PUBLIC
          "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
          "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <!-- Allow root to own the spotifyd interfaces (spotifyd runs as root in container) -->
  <policy user="root">
    <allow own_prefix="org.mpris.MediaPlayer2.spotifyd"/>
    <allow own_prefix="rs.spotifyd"/>
  </policy>

  <!-- Allow anyone to call methods on spotifyd (backend container needs this) -->
  <policy context="default">
    <allow send_destination_prefix="org.mpris.MediaPlayer2.spotifyd"/>
    <allow send_destination_prefix="rs.spotifyd"/>
    <allow receive_sender="org.mpris.MediaPlayer2.spotifyd"/>
    <allow receive_sender="rs.spotifyd"/>
  </policy>
</busconfig>
EOF

sudo systemctl reload dbus

# Configure Raspberry Pi HDMI display support
echo "Configuring HDMI display support..."

# Detect config.txt location (different on different Pi OS versions)
CONFIG_TXT=""
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_TXT="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_TXT="/boot/config.txt"
fi

if [ -n "$CONFIG_TXT" ]; then
    echo "Found config at: $CONFIG_TXT"

    # Backup config.txt if not already backed up
    if [ ! -f "${CONFIG_TXT}.gpt-home-backup" ]; then
        sudo cp "$CONFIG_TXT" "${CONFIG_TXT}.gpt-home-backup"
        echo "Backed up $CONFIG_TXT"
    fi

    # Add GPT Home HDMI configuration header if not present
    if ! grep -q "^# GPT Home HDMI configuration" "$CONFIG_TXT"; then
        echo "" | sudo tee -a "$CONFIG_TXT" > /dev/null
        echo "# GPT Home HDMI configuration" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi

    # Add HDMI force hotplug if not present (enables HDMI even without display at boot)
    if ! grep -q "^hdmi_force_hotplug=1" "$CONFIG_TXT"; then
        echo "Adding hdmi_force_hotplug=1 to $CONFIG_TXT"
        echo "hdmi_force_hotplug=1" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi

    # Force HDMI mode (not DVI) - required for audio over HDMI and proper signal detection
    if ! grep -q "^hdmi_drive=2" "$CONFIG_TXT"; then
        echo "Adding hdmi_drive=2 to $CONFIG_TXT"
        echo "hdmi_drive=2" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi

    # Ensure HDMI is not blanked
    if ! grep -q "^hdmi_blanking=0" "$CONFIG_TXT"; then
        echo "Adding hdmi_blanking=0 to $CONFIG_TXT"
        echo "hdmi_blanking=0" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi

    # Use vc4-kms-v3d for full KMS support (required for /dev/dri to exist)
    # Remove conflicting vc4-fkms-v3d overlay which doesn't create /dev/dri
    echo "Configuring display overlay for KMS/DRM support..."
    sudo sed -i '/dtoverlay=vc4-fkms-v3d/d' "$CONFIG_TXT"

    if ! grep -q "^dtoverlay=vc4-kms-v3d" "$CONFIG_TXT"; then
        echo "Adding dtoverlay=vc4-kms-v3d to $CONFIG_TXT"
        echo "dtoverlay=vc4-kms-v3d" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi

    echo -e "${GREEN}HDMI configuration updated. Changes will take effect after reboot.${NC}"
else
    echo -e "${YELLOW}Could not find config.txt - HDMI configuration skipped.${NC}"
fi

# Try to power on HDMI now if tvservice is available
if command -v tvservice >/dev/null 2>&1; then
    echo "Attempting to power on HDMI output..."
    sudo tvservice -p 2>/dev/null || true
    sleep 1
fi

if [ -e /dev/fb0 ]; then
    echo -e "${GREEN}Framebuffer detected at /dev/fb0 - display support available${NC}"
else
    echo -e "${YELLOW}No framebuffer detected yet. This is normal on Pi 5 with KMS driver.${NC}"
    echo "Display will be initialized via DRM when HDMI is connected."
fi

# Check DRM device access
echo "Checking DRM device access..."
if [ -d /dev/dri ]; then
    echo -e "${GREEN}DRM devices found:${NC}"
    ls -la /dev/dri/
    for card in /dev/dri/card*; do
        if [ -e "$card" ]; then
            if [ -r "$card" ] && [ -w "$card" ]; then
                echo -e "${GREEN}  $card - accessible${NC}"
            else
                echo -e "${YELLOW}  $card - fixing permissions...${NC}"
                sudo chmod 666 "$card"
            fi
        fi
    done
else
    echo -e "${YELLOW}/dev/dri not found - DRM devices will be available after HDMI connection${NC}"
fi

# Add user to video and render groups for DRM access
echo "Adding user to video and render groups for DRM access..."
sudo usermod -aG video $(whoami) 2>/dev/null || true
sudo usermod -aG render $(whoami) 2>/dev/null || true

echo -e "${GREEN}DRM display configuration complete.${NC}"



# Ensure framebuffer permissions
sudo chmod 666 /dev/fb* 2>/dev/null || true

# Clean up any old user-level Docker plugins (may be corrupted/outdated)
if [ -f "$HOME/.docker/cli-plugins/docker-buildx" ]; then
    echo "Removing old user-level buildx plugin..."
    rm -f "$HOME/.docker/cli-plugins/docker-buildx"
fi
if [ -f "$HOME/.docker/cli-plugins/docker-compose" ]; then
    echo "Removing old user-level compose plugin..."
    rm -f "$HOME/.docker/cli-plugins/docker-compose"
fi

# Verify Docker Buildx is available (installed via apt to /usr/libexec/docker/cli-plugins/)
if [ -f /usr/libexec/docker/cli-plugins/docker-buildx ]; then
    echo -e "${GREEN}Docker Buildx plugin installed${NC}"
else
    echo -e "${RED}ERROR: Docker Buildx plugin not found. Re-run script to install Docker properly.${NC}"
    exit 1
fi

# Setup UFW Firewall
echo "Setting up UFW Firewall..."
if which firewalld >/dev/null; then
    sudo systemctl stop firewalld
    sudo systemctl disable firewalld
    sudo yum remove firewalld -y 2>/dev/null || sudo apt-get remove firewalld -y 2>/dev/null || sudo zypper remove firewalld -y 2>/dev/null
fi
if ! which ufw >/dev/null; then
    sudo yum install ufw -y 2>/dev/null || sudo apt-get install ufw -y 2>/dev/null || sudo zypper install ufw -y 2>/dev/null
fi
sudo ufw allow ssh
sudo ufw allow 80,443/tcp
sudo ufw allow 5353/udp
sudo ufw allow 1234
echo "y" | sudo ufw enable

# Use docker compose (v2 plugin installed via apt to /usr/libexec/docker/cli-plugins/)
if [ -f /usr/libexec/docker/cli-plugins/docker-compose ]; then
    COMPOSE="docker compose"
    echo -e "${GREEN}Docker Compose plugin installed${NC}"
else
    echo -e "${RED}ERROR: Docker Compose plugin not found. Re-run script to install Docker properly.${NC}"
    exit 1
fi

# Parse flags
NO_BUILD=false
NO_CACHE=false
PRUNE=false

for arg in "$@"; do
    case $arg in
        --no-build) NO_BUILD=true ;;
        --no-cache) NO_CACHE=true ;;
        --prune) PRUNE=true ;;
    esac
done

if [[ "$NO_BUILD" == "false" ]]; then
    # Increase swap to prevent OOM during Docker build
    echo "Checking swap space for Docker build..."
    CURRENT_SWAP=$(free -m | awk '/^Swap:/ {print $2}')
    if [ "$CURRENT_SWAP" -lt 2048 ]; then
        echo -e "${YELLOW}Swap is ${CURRENT_SWAP}MB - increasing to 2GB for Docker build...${NC}"
        if [ -f /etc/dphys-swapfile ]; then
            sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
            sudo systemctl restart dphys-swapfile 2>/dev/null || sudo /etc/init.d/dphys-swapfile restart 2>/dev/null || true
            sleep 2
        elif [ ! -f /swapfile ]; then
            sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
            sudo chmod 600 /swapfile
            sudo mkswap /swapfile
            sudo swapon /swapfile
        fi
        echo -e "${GREEN}Swap configured: $(free -m | awk '/^Swap:/ {print $2}')MB${NC}"
    else
        echo -e "${GREEN}Swap is sufficient: ${CURRENT_SWAP}MB${NC}"
    fi

    [ -d ~/gpt-home ] && rm -rf ~/gpt-home
    git clone https://github.com/judahpaul16/gpt-home ~/gpt-home
    cd ~/gpt-home

    echo "Stopping any running gpt-home services..."
    $COMPOSE down 2>/dev/null || true

    if [[ "$PRUNE" == "true" ]]; then
        echo "Pruning Docker system..."
        docker system prune -af
        docker volume prune -f
    fi

    # Use the default docker driver for buildx (not docker-container which has network issues on Pi)
    # Remove any existing docker-container builders that cause network timeouts
    if docker buildx ls 2>/dev/null | grep -q "docker-container"; then
        echo "Removing docker-container builders (cause network issues on Pi)..."
        for builder in $(docker buildx ls --format '{{.Name}}' 2>/dev/null | grep -v default | grep -v "^\*"); do
            docker buildx rm "$builder" 2>/dev/null || true
        done
    fi
    docker buildx use default 2>/dev/null || true

    echo "Building and starting gpt-home with docker compose..."
    if [[ "$NO_CACHE" == "true" ]]; then
        DOCKER_DEFAULT_PLATFORM=linux/arm64 $COMPOSE build --no-cache
    else
        DOCKER_DEFAULT_PLATFORM=linux/arm64 $COMPOSE build
    fi

    if [ $? -ne 0 ]; then
        echo "Docker build failed. Exiting..."
        exit 1
    fi

    $COMPOSE up -d

    echo "gpt-home services are now running."
    $COMPOSE ps
fi

if [[ "$NO_BUILD" == "true" ]]; then
    [ -d ~/gpt-home ] && rm -rf ~/gpt-home
    git clone https://github.com/judahpaul16/gpt-home ~/gpt-home
    cd ~/gpt-home

    $COMPOSE down 2>/dev/null || true
    echo "Pulling and starting gpt-home from Docker Hub..."
    $COMPOSE pull
    $COMPOSE up -d

    $COMPOSE ps
fi
