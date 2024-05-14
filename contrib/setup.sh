#!/bin/bash

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
                sudo apt install -y docker.io
            else
                sudo apt install -y "$package"
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
}

install chrony
install nginx
install docker
install docker-buildx-plugin
install alsa-utils

# Create ALSA config (asound.conf, adjust as needed)
sudo cat > /etc/asound.conf <<EOF
pcm.!default { type plug; slave.pcm "dmix0"; }
ctl.!default { type hw; card 0; }
pcm.dmix0 { type dmix; ipc_key 1024; ipc_perm 0666; slave { pcm "hw:0,0"; channels 2; period_time 0; period_size 1024; buffer_size 4096; rate 48000; } bindings { 0 0; 1 1; } }
pcm.!hdmi { type plug; slave.pcm "dmix1"; }
ctl.!hdmi { type hw; card 1; }
pcm.dmix1 { type dmix; ipc_key 1025; ipc_perm 0666; slave { pcm "hw:1,0"; channels 2; period_time 0; period_size 1024; buffer_size 4096; rate 48000; } bindings { 0 0; 1 1; } }
EOF

# Install Docker Buildx plugin
DOCKER_BUILDX_PATH="$HOME/.docker/cli-plugins/docker-buildx"
mkdir -p "$(dirname "$DOCKER_BUILDX_PATH")"
curl -L "https://github.com/docker/buildx/releases/download/v0.10.4/buildx-v0.10.4.linux-arm64" -o "$DOCKER_BUILDX_PATH"
chmod +x "$DOCKER_BUILDX_PATH"

# Add current user to docker group
sudo usermod -aG docker $USER
# Check if the user is in the docker group
if ! groups $USER | grep -q "\bdocker\b"; then
    echo "User is not in the docker group. Please log out and log back in, then re-run this script."
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

sudo systemctl status nginx

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
    docker buildx build --platform linux/arm64 -t gpt-home . --load

    if [ $? -ne 0 ]; then
        echo "Docker build failed. Exiting..."
        exit 1
    fi

    echo "Container 'gpt-home' is now ready to run."

    echo "Running container 'gpt-home' from image 'gpt-home'..."
    docker run -d --name gpt-home \
        --privileged \
        --net=host \
        --tmpfs /run \
        --tmpfs /run/lock \
        -v ~/gpt-home:/app \
        -v /dev/snd:/dev/snd \
        -v /dev/shm:/dev/shm \
        -v /etc/asound.conf:/etc/asound.conf \
        -v /usr/share/alsa:/usr/share/alsa \
        -v /var/run/dbus:/var/run/dbus \
        -e OPENAI_API_KEY=$OPENAI_API_KEY \
        gpt-home

    echo "Container 'gpt-home' is now running."
fi

# Show status of the container
docker ps -a | grep gpt-home

# Show status of each service within the container
docker exec -it gpt-home systemctl status jackd
docker exec -it gpt-home systemctl status spotifyd
docker exec -it gpt-home systemctl status gpt-home
docker exec -it gpt-home systemctl status web-interface
