#!/bin/bash

# Function to check and install a package if it's not installed
check_and_install() {
    package=$1
    install_cmd=$2

    if ! dpkg -l | grep -q $package; then
        echo "Installing $package..."
        eval $install_cmd
    else
        echo "$package is already installed."
    fi
}

# Function to update the system time
update_system_time() {
    echo "Updating system time..."
    check_and_install "ntpdate" "sudo apt-get install -y ntpdate"
    sudo ntpdate -u ntp.ubuntu.com
}

# Update system time
update_system_time

# Update package list
yes | sudo add-apt-repository universe
sudo apt update

# Set permissions
sudo chown -R $(whoami):$(whoami) $HOME
sudo chmod -R 755 $HOME

# Check and install missing dependencies
check_and_install "python3" "sudo apt-get install -y python3 python3-dev python3-venv"
check_and_install "portaudio19-dev" "sudo apt-get install -y portaudio19-dev"
check_and_install "alsa-utils" "sudo apt-get install -y alsa-utils"
check_and_install "libjpeg-dev" "sudo apt-get install -y libjpeg-dev"
check_and_install "build-essential" "sudo apt-get install -y build-essential"
check_and_install "libasound2-dev" "sudo apt-get install -y libasound2-dev"
check_and_install "i2c-tools" "sudo apt-get install -y i2c-tools"
check_and_install "python3-smbus" "sudo apt-get install -y python3-smbus"
check_and_install "libespeak1" "sudo apt-get install -y libespeak1"
check_and_install "jackd2" "sudo apt-get install -y jackd2"
check_and_install "flac" "sudo apt-get install -y flac"
check_and_install "libflac12:armhf" "sudo apt-get install -y libflac12:armhf"
check_and_install "cmake" "sudo apt-get install -y cmake"
check_and_install "openssl" "sudo apt-get install -y openssl"
check_and_install "git" "sudo apt-get install -y git"
check_and_install "nginx" "sudo apt-get install -y nginx"
check_and_install "expect" "sudo apt-get install -y expect"
check_and_install "avahi-daemon" "sudo apt-get install -y avahi-daemon avahi-utils"
check_and_install "nodejs" "curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"

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

# Function to setup a systemd service
setup_service() {
    # Parameters
    local SERVICE_NAME=$1
    local EXEC_START=$2
    local DEPENDS=$3
    local ENV=$4
    local HOSTNAME=$5
    local TYPE=$6
    local LMEMLOCK=$7
    local RESTART=$8

    # Stop the service if it's already running
    sudo systemctl stop "$SERVICE_NAME" &>/dev/null

    echo "Creating and enabling $SERVICE_NAME..."
    # Create systemd service file
    cat <<EOF | sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null
[Unit]
Description=$SERVICE_NAME
$DEPENDS
StartLimitIntervalSec=10
StartLimitBurst=10

[Service]
User=$(whoami)
WorkingDirectory=/home/$(whoami)/gpt-home
$EXEC_START
$ENV
$HOSTNAME
$RESTART
$TYPE
$LMEMLOCK

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd to recognize the new service, then enable and restart it
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"

    # Wait for 5 seconds and then show the service status
    echo ""
    sleep 5
    sudo systemctl status "$SERVICE_NAME" --no-pager
    echo ""
}

# Setup UFW Firewall
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
sudo systemctl reload nginx

# Remove existing local repo if it exists
[ -d "gpt-home" ] && rm -rf gpt-home

# Clone gpt-home repo and navigate into its directory
git clone https://github.com/judahpaul16/gpt-home.git
cd gpt-home

## Setup main app
# Create and activate a virtual environment, then install dependencies
python3 -m venv env
source env/bin/activate
pip install --upgrade pip setuptools
pip install --use-pep517 -r requirements.txt

## Setup Web Interface
# Navigate to gpt-web and install dependencies
cd gpt-web
npm install

# Configure Avahi for gpt-home.local
sudo sed -i 's/#host-name=.*$/host-name=gpt-home/g' /etc/avahi/avahi-daemon.conf
sudo systemctl restart avahi-daemon

# Build the React App
npm run build

## Setup Services
# Setup spotifyd service
setup_service \
    "spotifyd.service" \
    "ExecStart=/usr/local/bin/spotifyd --no-daemon" \
    "Wants=sound.target
    After=sound.target
    Wants=network-online.target
    After=network-online.target" \
    "" \
    "" \
    "" \
    "" \
    "Restart=always
    RestartSec=12"

# Setup gpt-home service
setup_service \
    "gpt-home.service" \
    "ExecStart=/bin/bash -c 'source /home/$(whoami)/gpt-home/env/bin/activate && python /home/$(whoami)/gpt-home/app.py'" \
    "" \
    "Environment=\"OPENAI_API_KEY=$OPENAI_API_KEY\"" \
    "Environment=\"HOSTNAME=$HOSTNAME\"" \
    "Type=simple" \
    "LimitMEMLOCK=infinity" \
    "Restart=always"

# Setup FastAPI service for web interface backend
setup_service \
    "gpt-web.service" \
    "ExecStart=/bin/bash -c 'source /home/$(whoami)/gpt-home/env/bin/activate && uvicorn gpt-web.backend:app --host 0.0.0.0 --port 8000'" \
    "" \
    "Environment=\"OPENAI_API_KEY=$OPENAI_API_KEY\"" \
    "Environment=\"HOSTNAME=$HOSTNAME\"" \
    "Type=simple" \
    "" \
    "Restart=always"

# Mask systemd-networkd-wait-online.service to prevent boot delays
sudo systemctl mask systemd-networkd-wait-online.service