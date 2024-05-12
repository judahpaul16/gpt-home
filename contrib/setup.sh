#!/bin/bash

# Install system dependencies
function install() {
    local package=$1
    echo " Ensuring package '$package' is installed..."

    # Detect the package management system
    if command -v apt-get >/dev/null; then
        if ! dpkg -s "$package" >/dev/null 2>&1; then
            sudo add-apt-repository universe >/dev/null 2>&1 || true
            sudo apt update || true
            sudo apt install -y "$package"
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

if command -v apt-get >/dev/null ||
    command -v yum >/dev/null ||
    command -v dnf >/dev/null ||
    command -v zypper >/dev/null ||
    command -v pacman >/dev/null; then
        install chrony
        install docker
        install nginx
fi

# Prebuild Spotifyd
# Install cargo and rust
if ! command -v cargo &> /dev/null; then
    echo "Installing cargo and rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

    # Source the environment for cargo and rust
    if [ -f "$HOME/.cargo/env" ]; then
        source $HOME/.cargo/env
    else
        echo "Error: Unable to source Rust environment. Installation may have failed or path is incorrect."
    fi
else
    echo "cargo is already installed."
fi

# Ensure directory exists for the configuration
mkdir -p $HOME/.config/spotifyd

# Install spotifyd using Rust's Cargo
if ! command -v spotifyd &> /dev/null; then
    echo "Installing spotifyd..."
    cargo install spotifyd
    sudo mv $HOME/.cargo/bin/spotifyd /usr/local/bin/
else
    echo "spotifyd is already installed."
fi

# Create Spotifyd configuration (this is just a basic config; adjust accordingly)
cat <<EOF > $HOME/.config/spotifyd/spotifyd.conf
[global]
backend = "alsa" # Or pulseaudio if you use it
device_name = "GPT Home" # Name your device shows in Spotify Connect
bitrate = 320 # Choose bitrate from 96/160/320 kbps
cache_path = "/home/$(whoami)/.spotifyd/cache"
discovery = false
EOF

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

    echo "Building Docker image 'gpt-home'..."
    docker build --build-arg HOST_HOME="/home/$(whoami)" -t gpt-home .

    if [ $? -ne 0 ]; then
        echo "Docker build failed. Exiting..."
        exit 1
    fi

    echo "Running container 'gpt-home' from image 'gpt-home'..."
    docker run -d \
        --name gpt-home \
        --device /dev/snd:/dev/snd \
        --privileged \
        -p 8000:8000 \
        -v ~/gpt-home:/app \
        -e OPENAI_API_KEY=$OPENAI_API_KEY \
        gpt-home

    echo "Container 'gpt-home' is now running."
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
sudo tee /etc/nginx/sites-available/gpt-home <<EOF
server {
    listen 80;

    location / {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

# Remove existing symlink if it exists
[ -L "/etc/nginx/sites-enabled/gpt-home" ] && sudo unlink /etc/nginx/sites-enabled/gpt-home

# Symlink the site configuration
sudo ln -s /etc/nginx/sites-available/gpt-home /etc/nginx/sites-enabled

# Test the NGINX configuration
sudo nginx -t

# Remove the default site if it exists
[ -L "/etc/nginx/sites-enabled/default" ] && sudo unlink /etc/nginx/sites-enabled/default

# Reload NGINX to apply changes
sudo systemctl enable nginx
sudo systemctl reload nginx

sudo systemctl status nginx
docker ps -a
docker exec -it gpt-home supervisorctl status