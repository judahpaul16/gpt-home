# 🏠 GPT Home 🤖💬

![Ubuntu Server Version](https://img.shields.io/badge/Ubuntu_Server-v23.04-orange?style=flat-square&logo=ubuntu)
![Raspberry Pi Version](https://img.shields.io/badge/Raspberry_Pi-4B-red?style=flat-square&logo=raspberry-pi)
![Python Version](https://img.shields.io/badge/Python-v3.11-blue?style=flat-square&logo=python)
![Node.js Version](https://img.shields.io/badge/Node.js-v18.17.1-green?style=flat-square&logo=node.js)
[![Release](https://img.shields.io/github/v/release/judahpaul16/gpt-home?style=flat-square)](https://github.com/judahpaul16/gpt-home/tags)
[![Docker Pulls](https://img.shields.io/docker/pulls/judahpaul/gpt-home?style=flat-square)](https://hub.docker.com/r/judahpaul/gpt-home)

ChatGPT at home! Basically a better Google Nest Hub or Amazon Alexa home assistant. Built on the Raspberry Pi using the OpenAI API.

![My Build](screenshots/my_build.jpg)

This guide will explain how to build your own. It's pretty straight forward. You can also use this as a reference for building other projects on the Raspberry Pi.

* *Theoretically, the app should run on any linux system thanks to docker, but I can only vouch for the versions listed in the [compatibility table](#-compatibility). You should be able use any plug-and-play USB/3.5mm speaker or microphone as long as it's supported by [ALSA](https://www.alsa-project.org) or [PortAudio](http://www.portaudio.com/docs/v19-doxydocs/index.html).*

<table align="center">

<tr>
<td>
  
<table>
<th colspan="2" style="text-align: center;">📦 Integrations</th>
<tr>
<td>
      
✅ OpenAI  
✅ Spotify  
✅ Philips Hue  
✅ OpenWeatherMap  

</td>
<td>

🔲 Open-Meteo  
🔲 Alarms  
🔲 Reminders  
🔲 LiteLLM  

</td>
</tr>
</table>

</td>
<td>
    
<table>
<th colspan="2" style="text-align: center;">🔧 Use Cases
<tr>
<td>
      
🌈 Weather  
🌡️ Temperature  
🌅 Sunrise/Sunset  
📅 Calendar  

</td>
<td>

📚 General Knowledge  
🎵 Music  
💡 Lights  
😆 Fun & Games

</td>
</tr>
</table>

</td>
</tr>

</table>


## 🚀 TL;DR
```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/setup.sh | \
    bash -s -- --no-build
docker ps -aq -f name=gpt-home | xargs -r docker rm -f
docker pull judahpaul/gpt-home
docker run -d --name gpt-home \
    --device /dev/snd:/dev/snd \
    --privileged \
    -p 8000:8000 \
    -e OPENAI_API_KEY=your_key_here \
    judahpaul/gpt-home
```

## 🔌 Schematics
### ⚠️ Caution: Battery Connection
**IMPORTANT**: The image on the left is for illustration purposes. ***Do not connect the battery directly to the Raspberry Pi. Use a UPS or power supply with a battery like this [one](https://a.co/d/1rMMCPR).*** Connecting the battery directly to the Raspberry Pi can cause damage to the board from voltage fluctuations.

Before connecting the battery, ensure that the polarity is correct to avoid damage to your Raspberry Pi or other components. Disconnect power sources before making changes.

<table style="border-collapse: collapse; border: 0;">
  <tr>
    <td style="border: none;"><img src="screenshots/schematic_bb.png" alt="Schematics Breadboard" height="350px" /></td>
    <td style="border: none;"><img src="screenshots/schematic_schem.png" alt="Schematics Schematic" height="350px" /></td>
  </tr>
</table>
<span style="font-size: 1em; display:block;">[click to enlarge]</span>


---

## 🛠 My Parts List
This is the list of parts I used to build my first GPT Home. You can use this as a reference for building your own. I've also included optional parts that you can add to enhance your setup. ***To be clear you can use any system that runs Linux.***

<details>
<summary>👈 View My Parts List</summary>
<p>

**Core Components**  
- **Raspberry Pi 4B**: [Link](https://a.co/d/aH6YCXY) - $50-$70
- **Mini Speaker**: [Link](https://a.co/d/9bN8LZ2) - $18
- **128 GB MicroSD card**: [Link](https://a.co/d/0SxSg7O) - $13
- **USB 2.0 Mini Microphone**: [Link](https://a.co/d/eIrQUXC) - $8

---

**Optional Components**  
- **128x32 OLED Display**: [Link](https://a.co/d/4Scrfjq) - $13-$14
- **Standoff Spacer Column M3x40mm**: [Link](https://a.co/d/ees6oEA) - $14
- **M1.4 M1.7 M2 M2.5 M3 Screw Kit**: [Link](https://a.co/d/4XJwiBY) - $15
- **Raspberry Pi UPS Power Supply with Battery**: [Link](https://a.co/d/1rMMCPR) - $30
- **Cool Case for Raspberry Pi 4B**: [Link](https://a.co/d/idSKJIG) - $16

---

## 💲 Total Price Range
- **Core Components**: $102-$123
- **Optional Components**: $75
- **Total (Without Optional)**: $102-$123
- **Total (With Optional)**: $177-$198

---

</p>
</details>

## 📶 Configuring Wi-Fi via wpa_supplicant

To configure Wi-Fi on your Raspberry Pi, you'll need to edit the `wpa_supplicant.conf` file and ensure the wireless interface is enabled at boot. This method supports configuring multiple Wi-Fi networks and is suitable for headless setups.
*You could also use the [`raspi-config`](https://www.raspberrypi.com/documentation/computers/configuration.html) or the [`nmcli`](https://ubuntu.com/core/docs/networkmanager/configure-wifi-connections) utility to configure Wi-Fi; or simply use an Ethernet connection if you prefer.*

<details>
<summary>👈 View Instructions</summary>
<p>

**Step 1: Create the Bash Script**  

```bash
sudo nano /usr/local/bin/start_wifi.sh
```

Add the following content to the script:

```bash
#!/bin/bash

# Set the interface and SSID details
INTERFACE="wlan0"
SSID="your_wifi_ssid"
PASSWORD="your_wifi_password"

# Make sure no previous configuration interferes
sudo killall wpa_supplicant
sudo dhcpcd -x $INTERFACE

# Ensure the wireless interface is up
ip link set $INTERFACE up

# Create a wpa_supplicant configuration file
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
wpa_passphrase $SSID $PASSWORD > $WPA_CONF

# Start wpa_supplicant
wpa_supplicant -B -i $INTERFACE -c $WPA_CONF

# Obtain an IP address
dhcpcd $INTERFACE
```

Make sure to replace `your_wifi_ssid` and `your_wifi_password` with your actual WiFi network's SSID and password.

**Step 2: Make the Script Executable**  

```bash
sudo chmod +x /usr/local/bin/start_wifi.sh
```

**Step 3: Execute the Script at Boot**  

To run this script at boot time, you can add it to your `rc.local` file, which is executed by the init system at the end of each multiuser runlevel.

Edit the `rc.local` file:

```bash
sudo nano /etc/rc.local
```

Add the following line before the `exit 0` at the end of the file:

```bash
/usr/local/bin/start_wifi.sh &
```

Execute the script to start the Wi-Fi connection:

```bash
sudo /usr/local/bin/start_wifi.sh
```

Your Raspberry Pi should now connect to the Wi-Fi network automatically on boot.

If you want to connect to hidden networks or multiple networks, edit the `wpa_supplicant.conf` file located at `/etc/wpa_supplicant/wpa_supplicant.conf` and add the following configuration:

```bash
network={
    priority=1 # Higher priority networks are attempted first
    ssid="Your_Wi-Fi_Name"
    psk="Your_Wi-Fi_Password"
    key_mgmt=WPA-PSK
    scan_ssid=1 # Hidden network

    priority=2
    ssid="Enterprise_Wi-Fi_Name"
    key_mgmt=WPA-EAP
    eap=PEAP # or TTLS, TLS, FAST, LEAP
    identity="Your_Username"
    password="Your_Password" 
    phase1="peaplabel=0" # or "peapver=0" for PEAPv0
    phase2="auth=MSCHAPV2" # or "auth=MSCHAP" for MSCHAPv1
}
```

Restart the `wpa_supplicant` service to apply the changes:

```bash
sudo systemctl restart wpa_supplicant
```

See the [wpa_supplicant example file](https://w1.fi/cgit/hostap/plain/wpa_supplicant/wpa_supplicant.conf) for more information on the configuration options.

</p>
</details>

## 🛠 System Dependencies

Before running this project on your system, ensure your system clock is synchronized, your package lists are updated, and NGINX and Docker are installed. The setup script will take care of this for you but you can also do this manually.

<details>
<summary>👈 View Instructions</summary>
<p>

**Synchronize your system clock:**  
*Install `chrony` for time synchronization:*

```bash
sudo apt install -y chrony       # For Debian/Ubuntu
sudo yum install -y chrony       # For RHEL/CentOS/Alma
sudo dnf install -y chrony       # # For RHEL/CentOS/Alma 9^
sudo zypper install -y chrony    # For openSUSE
sudo pacman -S chrony            # For Arch Linux
```

Activate and synchronize time immediately with `chrony`:

```bash
sudo chronyc makestep
```

**Update your package list:**  
*Regular updates to your package list ensure access to the latest software and security patches.*

```bash
sudo apt update                   # For Debian/Ubuntu
sudo yum makecache                # For RHEL/CentOS/Alma
sudo dnf makecache                # For RHEL/CentOS/Alma 9^
sudo zypper refresh               # For openSUSE
sudo pacman -Sy                   # For Arch Linux
```

**Enable additional repositories:**  
*For systems that utilize EPEL and other special repositories, you may need to enable them to access a wider range of available packages.*

For Debian/Ubuntu:

```bash
sudo add-apt-repository universe
sudo apt update
```

For RHEL/CentOS/Alma and Fedora:

```bash
sudo yum install -y epel-release   # For RHEL/CentOS/Alma
sudo dnf install -y epel-release   # For RHEL/CentOS/Alma 9^
sudo yum makecache --timer            # For RHEL/CentOS/Alma
sudo dnf makecache --timer            # For RHEL/CentOS/Alma 9^
```

**Install Development Tools:**  
*Development tools are essential for building packages and compiling software. Ensure you have the necessary tools installed.*

For Debian/Ubuntu:

```bash
sudo apt install -y build-essential
```

For RHEL/CentOS/Alma and Fedora:

```bash
sudo yum groupinstall -y "Development Tools"   # For RHEL/CentOS/Alma 
sudo dnf groupinstall -y "Development Tools"   # For RHEL/CentOS/Alma 9^
```

**Install System Dependencies**  

1. **Docker**: Required for containerization.  
    ```bash
    sudo apt-get install -y docker  # For Debian/Ubuntu
    sudo yum install -y docker         # For RHEL/CentOS/Alma
    sudo dnf install -y docker         # For RHEL/CentOS/Alma 9^
    sudo zypper install -y docker      # For openSUSE
    sudo pacman -S docker              # For Arch Linux
    ```
    then `sudo systemctl enable --now docker`

2. **NGINX**: Required for reverse proxy for the web interface.  
    ```bash
    sudo apt-get install -y nginx   # For Debian/Ubuntu
    sudo yum install -y nginx       # For RHEL/CentOS/Alma
    sudo dnf install -y nginx       # For RHEL/CentOS/Alma 9^
    sudo zypper install -y nginx    # For openSUSE
    sudo pacman -S nginx            # For Arch Linux
    ```

</p>
</details>

---

## 🐳 Building the Docker Container
Before you run the setup script to build the container you should first export your `OPENAI_API_KEY` to an environment variable. The setup script will use this to initialize the container with your OpenAI API key.

***Note: Executing `export` directly in the terminal does not persist after reboot.***
```bash
export OPENAI_API_KEY="your_openai_api_key_here"
```

Alternatively, you can put this at the end of your `~/.bashrc` file. (recommended) 
```bash
# export your OpenAI API Key in here to initialize it at boot
export OPENAI_API_KEY="your_openai_api_key_here"

# Optional: Add these aliases to your .bashrc file for easier management
alias gpt-start="docker exec -it gpt-home supervisorctl start gpt-home"
alias gpt-restart="docker exec -it gpt-home supervisorctl restart gpt-home"
alias gpt-stop="docker exec -it gpt-home supervisorctl stop gpt-home"
alias gpt-status="docker exec -it gpt-home supervisorctl status gpt-home"
alias gpt-log="docker exec -it gpt-home tail -n 100 -f /app/src/events.log"

alias wi-start="docker exec -it gpt-home supervisorctl start web-interface"
alias wi-restart="docker exec -it gpt-home supervisorctl restart web-interface && sudo systemctl restart nginx"
alias wi-stop="docker exec -it gpt-home supervisorctl stop web-interface"
alias wi-status="docker exec -it gpt-home supervisorctl status web-interface"
alias wi-build="docker exec -it gpt-home cd /app/src/frontend && npm run build"
alias wi-log="tail -n 100 -f /var/log/nginx/access.log"
alias wi-error="tail -n 100 -f /var/log/nginx/error.log"

alias spotifyd-start="docker exec -it gpt-home supervisorctl start spotifyd"
alias spotifyd-restart="docker exec -it gpt-home supervisorctl restart spotifyd"
alias spotifyd-stop="docker exec -it gpt-home supervisorctl stop spotifyd"
alias spotifyd-disable="docker exec -it gpt-home supervisorctl disable spotifyd"
alias spotifyd-status="docker exec -it gpt-home supervisorctl status spotifyd"
alias spotifyd-enable="docker exec -it gpt-home supervisorctl enable spotifyd"
alias spotifyd-log="docker exec -it gpt-home tail -n 100 -f /var/log/spotifyd.log"
```
Run `source ~/.bashrc` to apply the changes to your current terminal session.

The setup script will take quite a while to run *(at least it did on my 1GB RAM Pi 4B)*. It will install all the dependencies and build the Docker container. However, you can skip the build process by passing the `--no-build` flag to the script; it will only install the dependencies and set up the firewall and NGINX. You can then pull the container from Docker Hub and run it.

```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/setup.sh | \
    bash -s -- --no-build
docker ps -aq -f name=gpt-home | xargs -r docker rm -f
docker pull judahpaul/gpt-home
docker run -d --name gpt-home \
    --device /dev/snd:/dev/snd \
    --privileged \
    -p 8000:8000 \
    -e OPENAI_API_KEY=your_key_here \
    judahpaul/gpt-home
```

***Note: For development purposes, running `setup.sh` without the `--no-build` flag mounts the project directory to the container by adding `-v ~/gpt-home:/app` to the `docker run` command. This allows you to make changes to the project files on your Raspberry Pi and see the changes reflected in the container.***

```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/setup.sh | \
    bash -s
```

### 🐚 setup.sh
If you prefer to run the setup script manually, you can do so. Create a script in your ***home*** folder with `vim ~/setup.sh` or `nano ~/setup.sh` and paste in the following:

<details>
<summary>👈 View Script</summary>
<p>

```bash
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

install chrony
install docker
install nginx

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

    echo "Building Docker image 'gpt-home'..."
    docker build -t gpt-home .

    if [ $? -ne 0 ]; then
        echo "Docker build failed. Exiting..."
        exit 1
    fi

    echo "Running container 'gpt-home' from image 'gpt-home'..."
    docker run -it \
        --name gpt-home \
        --device /dev/snd:/dev/snd \
        --privileged \
        --net=host \
        -v ~/gpt-home:/app \
        -e OPENAI_API_KEY=$OPENAI_API_KEY \
        gpt-home

    echo "Container 'gpt-home' is now running."
fi
```

</p>
</details>

Be sure to make the script executable to run it
```bash
chmod +x setup.sh
./setup.sh
```

---

## ✅ Compatibility

<table align="center">
<tr valign="top">
    <!-- Raspberry Pi -->
    <td>
    <table>
        <tr><th colspan="2">Raspberry Pi</th></tr>
        <tr><td>3B</td><td>✅</td></tr>
        <tr><td>3B+</td><td>✅</td></tr>
        <tr><td>4B</td><td>✅</td></tr>
        <tr><td>5</td><td>❔</td></tr>
        <tr><td>Zero 2 W</td><td>❔</td></tr>
        <tr><td>Orange Pi 3B</td><td>✅</td></tr>
    </table>
    </td>
    <!-- Python -->
    <td>
    <table>
        <tr><th colspan="2">Python</th></tr>
        <tr><td>3.7</td><td>❌</td></tr>
        <tr><td>3.8</td><td>✅</td></tr>
        <tr><td>3.9</td><td>✅</td></tr>
        <tr><td>3.10</td><td>✅</td></tr>
        <tr><td>3.11</td><td>✅</td></tr>
        <tr><td>3.12</td><td>❌</td></tr>
    </table>
    </td>
    <!-- Operating Systems -->
    <td>
    <table>
        <tr><th colspan="2">Operating System</th></tr>
        <tr><td>Ubuntu 22.04</td><td>✅</td></tr>
        <tr><td>Ubuntu 23.04</td><td>✅</td></tr>
        <tr><td>Ubuntu 24.04</td><td>✅</td></tr>
        <tr><td>Raspbian Buster</td><td>✅</td></tr>
        <tr><td>Raspbian Bullseye</td><td>✅</td></tr>
        <tr><td>Alma Linux 8</td><td>✅</td></tr>
        <tr><td>Alma Linux 9</td><td>✅</td></tr>
    </table>
    </td>
    <!-- Node.js -->
    <td>
    <table>
        <tr><th colspan="2">Node.js</th></tr>
        <tr><td>17.x</td><td>❔</td></tr>
        <tr><td>18.x</td><td>✅</td></tr>
        <tr><td>19.x</td><td>❔</td></tr>
        <tr><td>20.x</td><td>❔</td></tr>
        <tr><td>21.x</td><td>❔</td></tr>
        <tr><td>22.x</td><td>❔</td></tr>
    </table>
    </td>
</tr>
</table>

---

## 📚 Useful Documentation

<table align="center">
<tr>
<td>

- [OpenAI API Docs](https://platform.openai.com/docs/introduction)
- [Raspberry Pi Docs](https://www.raspberrypi.com/documentation)
- [Node.js Docs](https://nodejs.org/en/docs/)
- [npm Docs](https://docs.npmjs.com/)
- [NGINX Docs](https://nginx.org/en/docs/)
- [React Docs](https://reactjs.org/docs/getting-started.html)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Ubuntu Server Docs](https://ubuntu.com/server/docs)

</td>
<td>

- [GPIO Pinout](https://www.raspberrypi.com/documentation/computers/images/GPIO-Pinout-Diagram-2.png)
- [Adafruit SSD1306 Docs](https://circuitpython.readthedocs.io/projects/ssd1306/en/latest/)
- [pyttsx3 Docs](https://pypi.org/project/pyttsx3/)
- [I2C Docs](https://i2c.readthedocs.io/en/latest/)
- [ALSA Docs](https://www.alsa-project.org/wiki/Documentation)
- [PortAudio Docs](http://www.portaudio.com/docs/v19-doxydocs/index.html)
- [SpeechRecognition Docs](https://pypi.org/project/SpeechRecognition/)
- [Docker Docs](https://docs.docker.com/)

</td>
<td>

- [Spotify API Docs](https://developer.spotify.com/documentation/web-api/)
- [Spotify API Python Docs (Spotipy)](https://spotipy.readthedocs.io/)
- [Spotifyd Docs](https://docs.spotifyd.rs/)
- [Phillips Hue API Docs](https://developers.meethue.com/develop/get-started-2/)
- [Phillips Hue Python API Docs](https://github.com/studioimaginaire/phue)
- [OpenWeatherMap API Docs](https://openweathermap.org/api/one-call-3)
- [Open-Meteo API Docs](https://open-meteo.com/en/docs)
- [Fritzing Schematics](https://fritzing.org/)

</td>
</tr>
</table>

---

## 🤝 Contributing
Contributions are certainly welcome! Please read the [contributing guidelines](CONTRIBUTING.md) for more information on how to contribute.

## 📜 License
This project is licensed under the GNU GPL v3.0 License - see the [LICENSE](LICENSE) file for details.
