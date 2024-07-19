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
install nginx
install containerd
install docker
install docker-buildx-plugin
install alsa-utils
sudo systemctl enable docker
sudo systemctl start docker

# Create ALSA config (asound.conf, adjust as needed)
sudo tee /etc/asound.conf > /dev/null <<EOF
pcm.!default { type hw card Headphones device 0 }
ctl.!default { type hw card Headphones }
EOF

# Install Docker Buildx plugin
mkdir -p $HOME/.docker/cli-plugins
curl -Lo $HOME/.docker/cli-plugins/docker-buildx https://github.com/docker/buildx/releases/download/v0.14.0/buildx-v0.14.0.linux-arm64
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
echo "y" | sudo ufw enable

# Setup NGINX for reverse proxy
echo "Setting up NGINX..."
sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
sudo tee /etc/nginx/sites-available/gpt-home <<EOF
server {
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

# Remove gpt-home site symlink if it exists
[ -L "/etc/nginx/sites-enabled/gpt-home" ] && sudo unlink /etc/nginx/sites-enabled/gpt-home

# Remove the default site if it exists
[ -L "/etc/nginx/sites-enabled/default" ] && sudo unlink /etc/nginx/sites-enabled/default

# Create a symlink to the gpt-home site and reload NGINX
sudo ln -s /etc/nginx/sites-available/gpt-home /etc/nginx/sites-enabled
sudo systemctl enable nginx
sudo nginx -t && sudo systemctl restart nginx

sudo systemctl status --no-pager nginx

if [[ "$1" != "--no-build" ]]; then
    [ -d ~/gpt-home ] && rm -rf ~/gpt-home
    git clone https://github.com/judahpaul16/gpt-home ~/gpt-home
    cd ~/gpt-home
    echo "Checking if the container 'gpt-home' is already running..."
    if [ $(docker ps -q -f name=gpt-home) ]; then
        echo "Stopping running container 'gpt-home'..."
        docker stop gpt-home
    fi

    echo "Checking for existing container 'gpt-home'..."
    if [ $(docker ps -aq -f status=exited -f name=gpt-home) ]; then
        echo "Removing existing container 'gpt-home'..."
        docker rm -f gpt-home
    fi

    echo "Pruning Docker system..."
    docker system prune -f

    # Check if the buildx builder exists, if not create and use it
    if ! docker buildx ls | grep -q mybuilder; then
        docker buildx create --name mybuilder --use
        docker buildx inspect --bootstrap
    fi

    # Building Docker image 'gpt-home' for ARMhf architecture
    echo "Building Docker image 'gpt-home' for ARMhf..."
    timeout 3600 docker buildx build --platform linux/arm64 -t gpt-home --load .

    if [ $? -ne 0 ]; then
        echo "Docker build failed. Exiting..."
        exit 1
    fi

    echo "Container 'gpt-home' is now ready to run."

    echo "Running container 'gpt-home' from image 'gpt-home'..."
    docker run --restart unless-stopped -d --name gpt-home \
        --mount type=bind,source=/etc/asound.conf,target=/etc/asound.conf \
        --privileged \
        --net=host \
        --tmpfs /run \
        --tmpfs /run/lock \
        -v ~/gpt-home:/app \
        -v /dev/snd:/dev/snd \
        -v /dev/shm:/dev/shm \
        -v /usr/share/alsa:/usr/share/alsa \
        -v /var/run/dbus:/var/run/dbus \
        -e OPENAI_API_KEY=$OPENAI_API_KEY \
        -e LITELLM_API_KEY=$LITELLM_API_KEY \
        gpt-home

    echo "Container 'gpt-home' is now running."

    # Show status of the container
    docker ps -a | grep gpt-home

    sleep 10

    # Show status of all programs managed by Supervisor
    docker exec -i gpt-home supervisorctl status
fi

if [[ "$1" == "--no-build" ]]; then
    docker ps -aq -f name=gpt-home | xargs -r docker rm -f
    docker pull judahpaul/gpt-home
    docker run --restart unless-stopped -d --name gpt-home \
        --mount type=bind,source=/etc/asound.conf,target=/etc/asound.conf \
        --privileged \
        --net=host \
        --tmpfs /run \
        --tmpfs /run/lock \
        -v /dev/snd:/dev/snd \
        -v /dev/shm:/dev/shm \
        -v /usr/share/alsa:/usr/share/alsa \
        -v /var/run/dbus:/var/run/dbus \
        -e OPENAI_API_KEY=$OPENAI_API_KEY \
        -e LITELLM_API_KEY=$LITELLM_API_KEY \
        judahpaul/gpt-home
    docker ps -a | grep gpt-home
    sleep 10
    docker exec -i gpt-home supervisorctl status
fi