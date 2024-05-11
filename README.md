# 🏠 GPT Home 🤖💬

![Ubuntu Server Version](https://img.shields.io/badge/Ubuntu_Server-v23.04-orange?style=flat-square&logo=ubuntu)
![Raspberry Pi Version](https://img.shields.io/badge/Raspberry_Pi-4B-red?style=flat-square&logo=raspberry-pi)
![Python Version](https://img.shields.io/badge/Python-v3.11-blue?style=flat-square&logo=python)
![Node.js Version](https://img.shields.io/badge/Node.js-v18.17.1-green?style=flat-square&logo=node.js)
[![Release](https://img.shields.io/github/v/release/judahpaul16/gpt-home?style=flat-square)](https://github.com/judahpaul16/gpt-home/tags)
[![Docker Pulls](https://img.shields.io/docker/pulls/judahpaul16/gpt-home?style=flat-square)](https://hub.docker.com/r/judahpaul16/gpt-home)

ChatGPT at home! Basically a better Google Nest Hub or Amazon Alexa home assistant. Built on the Raspberry Pi using the OpenAI API.

![My Build](screenshots/my_build.jpg)

This guide will explain how to build your own. It's pretty straight forward. You can also use this as a reference for building other projects on the Raspberry Pi.

* *Theoretically, the app should run on any linux system thanks to docker, but I can only vouch for the versions listed in the [compatibility table](#-compatibility). You should be able use any plug-and-play USB/3.5mm speaker or microphone as long as it's supported by [ALSA](https://www.alsa-project.org).*

### 🔌 Integrations
<table>
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

## 🚀 TL;DR
```bash
cd ~
if ! grep -q "OPENAI_API_KEY" ~/.bashrc; then
    echo 'export OPENAI_API_KEY="your_openai_api_key"' >> ~/.bashrc
fi
source ~/.bashrc
docker ps -aq -f name=gpt-home | xargs -r docker rm -f
docker pull judahpaul/gpt-home
docker run -d --name gpt-home --device /dev/snd:/dev/snd --privileged -p 8000:8000 judahpaul/gpt-home
curl -s https://raw.githubusercontent.com/judahpaul/gpt-home/main/contrib/setup.sh | bash -s -- --no-build
```

## Schematics / Wiring Diagram
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

## 📶 Configuring Wi-Fi via wpa_supplicant

To configure Wi-Fi on your Raspberry Pi, you'll need to edit the `wpa_supplicant.conf` file and ensure the wireless interface is enabled at boot. You could also use the `raspi-config` or the `nmcli` utility to configure Wi-Fi or simply use an Ethernet connection.

1. Install `net-tools` to get the `ifconfig` command:
   ```bash
   sudo apt install net-tools
   ```

2. To enable the wireless interface (`wlan0` in most cases) at boot, add the following command to `/etc/rc.local` before the `exit 0` line:  
    *Create the file if it doesn't exist*
    ```bash
    sudo vim /etc/rc.local
    ```
    Add the following contents:
    ```bash
    #!/bin/bash
    sudo ifconfig wlan0 up &
    sudo wpa_supplicant -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf -B &
    sudo dhclient wlan0 &
    exit 0
    ```
    Ensure the file has executable permissions and is enabled as a service:
    ```bash
    sudo chmod +x /etc/rc.local
    sudo systemctl enable rc-local.service
    sudo systemctl start rc-local.service
    ```

3. Open the configuration file in a text editor:
    ```bash
    sudo vim /etc/wpa_supplicant/wpa_supplicant.conf
    ```

4. Add the following lines at the end of the file:  
*You can define multiple `network` blocks for multiple Wi-Fi networks*
    ```bash
    network={
        ssid="Your_Wi-Fi_Name"
        psk="Your_Wi-Fi_Password"
        key_mgmt=WPA-PSK
    }
    ```
    Replace `Your_Wi-Fi_Name` and `Your_Wi-Fi_Password` with your actual Wi-Fi credentials.

4. Ensure `wpa_supplicant` service starts at boot:
    ```bash
    sudo systemctl enable wpa_supplicant.service
    ```

5. Start `wpa_supplicant` service:
    ```bash
    sudo systemctl start wpa_supplicant.service
    ```

Your Raspberry Pi should now connect to the Wi-Fi network automatically on boot. If you face issues, refer to the [official Raspberry Pi documentation on wireless connectivity](https://www.raspberrypi.com/documentation/computers/configuration.html#setting-up-a-wireless-lan-via-the-command-line).

## 🛠 System Dependencies

Before running this project on your system, ensure some system-level dependencies are installed alongside the Python packages. These instructions are adaptable across various Linux distributions.

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
sudo yum makecache fast            # For RHEL/CentOS/Alma
sudo dnf makecache fast            # For RHEL/CentOS/Alma 9^
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
*The [setup script](#-building-the-docker-container) will handle the application dependencies.*

1. **OpenAI API Key**: Required for OpenAI's GPT API.  
    Setup: Set up as an environment variable.  

2. **Docker**: Required for containerization.  
    ```bash
    sudo apt-get install -y docker.io
    sudo systemctl enable --now docker
    ```

3. **NGINX**: Required for reverse proxy for the web interface.  
    ```bash
    sudo apt-get install -y nginx   # For Debian/Ubuntu
    sudo yum install -y nginx       # For RHEL/CentOS/Alma
    sudo dnf install -y nginx       # For RHEL/CentOS/Alma 9^
    sudo zypper install -y nginx    # For openSUSE
    sudo pacman -S nginx            # For Arch Linux
    ```

---

## 🐳 Building the Docker Container
Before you run the script to build the container you must first export your `OPENAI_API_KEY`. The first time you run it, it will take a while to install all the dependencies. The script is platform-agnostic and should work on any Linux system.

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
alias gpt-log="docker exec -it gpt-home tail -n 100 -f /path/to/your/application/logs/events.log"

alias web-start="docker exec -it gpt-home supervisorctl start gpt-web"
alias web-restart="docker exec -it gpt-home supervisorctl restart gpt-web && sudo systemctl restart nginx"
alias web-stop="docker exec -it gpt-home supervisorctl stop gpt-web"
alias web-status="docker exec -it gpt-home supervisorctl status gpt-web"
alias web-log="tail -n 100 -f /var/log/nginx/access.log"
alias web-error="tail -n 100 -f /var/log/nginx/error.log"

alias spotifyd-start="docker exec -it gpt-home supervisorctl start spotifyd"
alias spotifyd-restart="docker exec -it gpt-home supervisorctl restart spotifyd"
alias spotifyd-stop="docker exec -it gpt-home supervisorctl stop spotifyd"
alias spotifyd-disable="docker exec -it gpt-home supervisorctl disable spotifyd"
alias spotifyd-status="docker exec -it gpt-home supervisorctl status spotifyd"
alias spotifyd-enable="docker exec -it gpt-home supervisorctl enable spotifyd"
alias spotifyd-log="docker exec -it gpt-home tail -n 100 -f /var/log/spotifyd.log"
```
Run `source ~/.bashrc` to apply the changes to your current terminal session.

## 🐚 setup.sh
Create a script in your ***home*** folder with `vim ~/setup.sh` and paste in the following:

```bash
#!/bin/bash

echo "Checking if the container 'gpt-home' is already running..."
if [ $(docker ps -q -f name=gpt-home) ]; then
    echo "Stopping running container 'gpt-home'..."
    docker stop gpt-home
fi

echo "Checking for existing container 'gpt-home'..."
if [ $(docker ps -aq -f status=exited -f name=gpt-home) ]; then
    echo "Removing existing container 'gpt-home'..."
    docker rm gpt-home
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
docker run -d \
    --name gpt-home \
    --device /dev/snd:/dev/snd \
    --privileged \
    -p 8000:8000 \
    gpt-home

echo "Container 'gpt-home' is now running."
```

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
