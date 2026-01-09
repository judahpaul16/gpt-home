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

# Function to install system dependencies
function install() {
    local package=$1
    echo "Ensuring package '$package' is installed..."

    # Detect the package management system
    if command -v apt-get >/dev/null; then
        if ! dpkg -s "$package" >/dev/null 2>&1; then
            sudo yes | add-apt-repository universe >/dev/null 2>&1 || true
            sudo apt update || true
            if [ "$package" == "docker" ]; then
                sudo apt-get install -y docker.io
            else
                sudo apt-get install -y "$package"
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
        if ! docker ps >/dev/null 2>&1; then
            echo "Docker installed. Adding $(whoami) to the 'docker' group..."
            sudo usermod -aG docker $(whoami)
            echo -e "${RED}User added to \`docker\` group but the session must be reloaded to access the Docker daemon. Please log out, log back in, and rerun the script. Exiting...${NC}"
            exit 0
        fi
    fi
}

install chrony
install containerd
install docker
install docker-buildx-plugin
install docker-compose-plugin
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
echo -e "${CYAN}The app renders directly to /dev/dri via SDL2 KMSDRM - no compositor needed.${NC}"
echo -e "${CYAN}Just run: docker compose up -d${NC}"

# Install Docker Buildx plugin
mkdir -p $HOME/.docker/cli-plugins
curl -Lo $HOME/.docker/cli-plugins/docker-buildx https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-arm64
sudo chmod +x $HOME/.docker/cli-plugins/docker-buildx
docker buildx version

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

# Determine docker-compose command (v2 plugin vs v1 standalone)
if docker-compose version &>/dev/null; then
    COMPOSE="docker-compose"
elif docker-compose version &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "Installing docker-compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    COMPOSE="docker-compose"
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

    # Check if the buildx builder exists, if not create and use it
    if ! docker buildx ls | grep -q mybuilder; then
        docker buildx create --name mybuilder --use
        docker buildx inspect --bootstrap
    fi

    echo "Building and starting gpt-home with docker-compose..."
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
