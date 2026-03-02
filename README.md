# 🏠 GPT Home 🤖💬

![Ubuntu Server Version](https://img.shields.io/badge/Ubuntu_Server-v24.04-orange?style=flat-square&logo=ubuntu)
![Raspberry Pi Version](https://img.shields.io/badge/Raspberry_Pi-4B-red?style=flat-square&logo=raspberry-pi)
![Python Version](https://img.shields.io/badge/Python-v3.11-blue?style=flat-square&logo=python)
![Node.js Version](https://img.shields.io/badge/Node.js-v18.17.1-green?style=flat-square&logo=node.js)
[![Release](https://img.shields.io/github/v/release/judahpaul16/gpt-home?style=flat-square)](https://github.com/judahpaul16/gpt-home/tags)

ChatGPT at home! Basically a better Google Nest Hub or Amazon Alexa home assistant. Built on the Raspberry P iusing LiteLLM and LangGraph.

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
✅ Open-Meteo  
✅ Alarms  
✅ Reminders  

</td>
<td>

✅ Calendar (CalDAV)  
✅ LiteLLM  
✅ LangGraph  
✅ Persistent Memory  
✅ Display Support  
🔲 Zigbee2MQTT  

</td>
</tr>
</table>

</td>
<td>
    
<table>
<th colspan="2" style="text-align: center;">🔧 Use Cases
<tr>
<td>
      
☁️ Weather  
⏰ Alarms  
⌚ Reminders  
📆 Calendar  
☑️ To-Do List

</td>
<td>

📚 General Knowledge  
🗣️ Translation  
🎵 Music  
💡 Lights  
😆 Fun & Games

</td>
</tr>
</table>

</td>
</tr>

</table>

> 📖 **Developer Documentation**: For in-depth technical documentation, architecture details, and API references, visit the [**GPT Home Wiki**](https://github.com/judahpaul16/gpt-home/wiki).

## 🚀 TL;DR

### Production (Raspberry Pi)
1. Run the setup script:
```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/setup.sh | \
    bash -s -- --no-build
```
2. ***Required:*** Set your API key. Copy the example config and add your key. GPT Home uses **LiteLLM** which supports 100+ providers (OpenAI, Anthropic, Google, Cohere, etc.):
```bash
cd ~/gpt-home
cp .env.example .env
sed -i 's/^LITELLM_API_KEY=$/LITELLM_API_KEY=your-api-key-here/' .env
docker compose down && docker compose up -d
```

> **Tip:** You can also set the API key via the web interface at `gpt-home.local/settings`. See [LiteLLM docs](https://docs.litellm.ai/docs/providers) for all supported providers.

3. ***Optional:*** To view the logs and verify the assistant is running:
```bash
docker compose logs -f
```

### Development (Any Machine)
```bash
git clone https://github.com/judahpaul16/gpt-home.git
cd gpt-home
cp .env.example .env
# Edit .env with your API keys
nano .env
# Start dev environment with hot reload
COMPOSE_PROFILES=dev docker compose up
# or
docker compose --profile dev up
```
Access at `http://localhost` (nginx routes to frontend and API).

## 🔌 Schematics
### ⚠️ Caution: Battery Connection
**IMPORTANT**: The image on the left is for illustration purposes. ***Do not connect the battery directly to the Raspberry Pi. Use a UPS or power supply with a battery like this [one](https://www.amazon.com/dp/B0C1GFX5LW?_encoding=UTF8&psc=1&ref_=cm_sw_r_cp_ud_dp_Z9X3PJZ7ZB8PCX42WHA6).*** Connecting the battery directly to the Raspberry Pi can cause damage to the board from voltage fluctuations.

Before connecting the battery, ensure that the polarity is correct to avoid damage to your Raspberry Pi or other components. Disconnect power sources before making changes.

<table style="border-collapse: collapse; border: 0;">
  <tr>
    <td style="border: none;"><img src="screenshots/schematic_bb.png" alt="Schematics Breadboard" height="350px" /></td>
    <td style="border: none;"><img src="screenshots/schematic_schem.png" alt="Schematics Schematic" height="350px" /></td>
  </tr>
</table>
<span style="font-size: 1em; display:block;">[click to enlarge]</span>


---

## 📋 Specifications

|  | Minimum | Recommended |
|---|---|---|
| **Board** | Raspberry Pi Zero 2 W | Raspberry Pi 4B / 5 |
| **CPU** | Quad-core ARM Cortex-A53 @ 1GHz | Quad-core ARM Cortex-A72 @ 1.5GHz+ |
| **RAM** | 512MB | 1GB+ |
| **Storage** | 16GB microSD | 32GB+ microSD |
| **OS** | Raspberry Pi OS Lite (64-bit) | Ubuntu Server (64-bit) |

> All system dependencies (Docker, time sync, etc.) are installed automatically by the setup script.

## 🛠 My Parts List
This is the list of parts I used to build my first GPT Home. You can use this as a reference for building your own. I've also included optional parts that you can add to enhance your setup. ***To be clear you can use any system that runs Linux.***

<details>
<summary>👈 View My Parts List</summary>
<p>

**Core Components**
- **Raspberry Pi 4B**: [Link](https://www.amazon.com/dp/B07TD43PDZ) - $50-$70
- **Mini Speaker**: [Link](https://www.amazon.com/dp/B01HB18IZ4) - $18
- **128 GB MicroSD card**: [Link](https://www.amazon.com/dp/B09X7BK27V) - $13
- **USB 2.0 Mini Microphone**: [Link](https://www.amazon.com/dp/B01KLRBHGM) - $8

---

**Alternative Boards**
- **Raspberry Pi Zero 2 W**: [Link](https://www.amazon.com/dp/B09LH5SBPS) - ~$15
- **Orange Pi Zero 2W (2GB)**: [Link](https://www.amazon.com/dp/B0CHM6XND9) - ~$20

---

**Audio HATs**
- **Whisplay HAT** (audio + display expansion for Pi Zero): [Link](https://www.amazon.com/dp/B0FPG8S6K6) - ~$36
- **RaspiAudio Ultra++** (DAC + speaker + mic, all Pi models): [Link](https://www.amazon.com/dp/B08HVQQSWP) - ~$35

---

**Optional Components**
- **128x32 I2C Display**: [Link](https://www.amazon.com/dp/B08CDN5PSJ) - $13-$14
- **3.5" PiScreen Display (480x320)**: [Link](https://www.amazon.com/dp/B0BJDTL9J3) - $15-$20 (SPI, ILI9486) — auto-detected by setup script
- **7" HDMI Touchscreen**: [Link](https://www.amazon.com/Hosyond-Display-1024%C3%97600-Capacitive-Raspberry/dp/B09XKC53NH) - $40-$60 (1024x600)
- **PiSugar2 Battery** (1200mAh UPS for Pi Zero): [Link](https://www.amazon.com/dp/B08D678XPR) - ~$36
- **Standoff Spacer Column M3x40mm**: [Link](https://www.amazon.com/dp/B07M7D8HMT) - $14
- **M1.4 M1.7 M2 M2.5 M3 Screw Kit**: [Link](https://www.amazon.com/dp/B08KXS2MWG) - $15
- **Raspberry Pi UPS Power Supply with Battery**: [Link](https://www.amazon.com/dp/B0C1GFX5LW) - $30
- **Cool Case for Raspberry Pi 4B**: [Link](https://www.amazon.com/dp/B07TTN1M7G) - $16

---

</p>
</details>

## 📶 Configuring Wi-Fi

If your Pi isn't connected via Ethernet, use the included Wi-Fi setup script. It configures `wpa_supplicant` + `systemd-networkd`, disables NetworkManager (which can interfere), sets up DNS, and disables Wi-Fi power saving:

```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/wifi-setup.sh | \
    sudo WIFI_SSID="your-ssid" WIFI_PSK="your-password" bash
```

Or run it interactively (prompts for SSID and password):

```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/wifi-setup.sh | \
    sudo bash
```

You can also set `WIFI_IFACE` (default: `wlan0`) and `WIFI_COUNTRY` (default: `US`) if needed.

<details>
<summary>👈 Other methods</summary>
<p>

**NetworkManager (Ubuntu, Armbian, some Raspberry Pi OS images):**

```bash
sudo nmcli dev wifi connect "your-ssid" password "your-password"
```

To list available networks: `nmcli dev wifi list`

**raspi-config (Raspberry Pi OS):**

```bash
sudo raspi-config
```

Navigate to **System Options** > **Wireless LAN** and enter your SSID and password.

**Ethernet:** If Wi-Fi is unreliable, a wired Ethernet connection is always the most stable option and requires no configuration.

</p>
</details>

---

## 🐳 Building the Docker Container
***Note: GPT Home uses LiteLLM which supports 100+ LLM providers. Set your `LITELLM_API_KEY` in the `.env` file or via the web interface at `gpt-home.local/settings`. See the [LiteLLM docs](https://docs.litellm.ai/docs/providers) for supported providers.***

***Optional: Add these aliases to your .bashrc file for easier management.***
```bash
# Set working directory
alias gpt-home="cd ~/gpt-home"

# Manage all services
alias gpt-up="cd ~/gpt-home && docker compose up -d"
alias gpt-down="cd ~/gpt-home && docker compose down"
alias gpt-restart="cd ~/gpt-home && docker compose restart"
alias gpt-logs="cd ~/gpt-home && docker compose logs -f"
alias gpt-status="cd ~/gpt-home && docker compose ps"

# Manage individual services
alias gpt-backend-logs="cd ~/gpt-home && docker compose logs -f backend"
alias gpt-backend-restart="cd ~/gpt-home && docker compose restart backend"
alias gpt-backend-shell="cd ~/gpt-home && docker compose exec backend bash"

alias gpt-frontend-logs="cd ~/gpt-home && docker compose logs -f frontend"
alias gpt-frontend-restart="cd ~/gpt-home && docker compose restart frontend"

alias gpt-nginx-logs="cd ~/gpt-home && docker compose logs -f nginx"
alias gpt-nginx-restart="cd ~/gpt-home && docker compose restart nginx"

alias gpt-spotify-logs="cd ~/gpt-home && docker compose logs -f spotify"
alias gpt-spotify-restart="cd ~/gpt-home && docker compose restart spotify"

# Development mode (hot reload)
alias gpt-dev="cd ~/gpt-home && docker compose --profile dev up"
```
Run `source ~/.bashrc` to apply the changes to your current terminal session.

The setup script will take quite a while to run ***(900.0s+ to build and setup dependencies on my quad-core Raspberry Pi 4B w/ 1G RAM)***. It will install all the dependencies and build the Docker containers. However, you can skip the build process by passing the `--no-build` flag to the script; it will install the dependencies, set up the firewall, and pull the containers from Docker Hub and run them.

```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/setup.sh | \
    bash -s -- --no-build
```

**Alternatively, for development purposes, running `setup.sh` without the `--no-build` flag builds all the service images locally. This is useful for testing changes to the codebase.**

```bash
curl -s https://raw.githubusercontent.com/judahpaul16/gpt-home/main/contrib/setup.sh | \
    bash -s
```

You can also access a shell inside a running container for debugging:

```bash
docker compose exec backend bash   # Voice assistant container
docker compose exec frontend bash  # Web server container
docker compose exec nginx sh       # NGINX container
```

**Explanation of Docker Compose Configuration**

The `docker-compose.yml` configures six services:

```yaml
services:
  db:
    # PostgreSQL with pgvector for persistent memory storage
    image: pgvector/pgvector:0.8.1-pg18-trixie
    volumes:
      - postgres-data:/var/lib/postgresql/data

  nginx:
    # Reverse proxy - routes /api, /logs, /settings to backend; static to frontend
    image: nginx:alpine
    ports: ["80:80"]
    depends_on: [backend]

  backend:
    # Voice assistant (app.py) + FastAPI backend (backend.py) on :8000
    image: judahpaul/gpt-home-backend:latest
    privileged: true
    expose: ["8000"]
    devices: ["/dev/snd:/dev/snd", "/dev/i2c-1:/dev/i2c-1", "/dev/dri:/dev/dri"]

  frontend:             # Production (profile: prod)
    # Multi-stage build: React static files served by nginx
    image: judahpaul/gpt-home-frontend:latest
    expose: ["80"]

  frontend-dev:         # Development (profile: dev)
    # React dev server with hot reload
    build: compose/web/Dockerfile.dev
    expose: ["80"]
    volumes:
      - ./src/frontend:/app  # Hot reload

  spotify:
    # Spotify Connect + Avahi mDNS
    image: judahpaul/gpt-home-spotify:latest
    network_mode: host  # Required for mDNS discovery
```

> **Profiles:** By default, `COMPOSE_PROFILES=prod` is set in `.env`, so `frontend` runs. For development with hot reload, use `docker compose --profile dev up`.

**Setup Script Flags**

The `setup.sh` script supports the following flags:

| Flag | Description |
|------|-------------|
| `--no-build` | Skip building and pull the pre-built image from Docker Hub instead |
| `--no-cache` | Build without using Docker's cache (forces fresh build) |
| `--prune` | Prune Docker system and volumes before building (cleans up disk space) |

**Examples:**
```bash
# Default build (uses cache, no prune)
./setup.sh

# Pull from Docker Hub without building
./setup.sh --no-build

# Fresh build without cache
./setup.sh --no-cache

# Full cleanup and fresh build
./setup.sh --prune --no-cache
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
        <tr><td>Zero 2 W</td><td>✅</td></tr>
        <tr><td>Orange Pi 3B</td><td>✅</td></tr>
        <tr><td>Orange Pi Zero 2W</td><td>✅</td></tr>
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
        <tr><td>Ubuntu 23.04</td><td>✅ (EOL)</td></tr>
        <tr><td>Ubuntu 24.04</td><td>✅</td></tr>
        <tr><td>Ubuntu 25.04</td><td>✅</td></tr>
        <tr><td>Debian Buster</td><td>✅</td></tr>
        <tr><td>Debian Bullseye</td><td>✅</td></tr>
        <tr><td>Alma Linux 8</td><td>✅</td></tr>
        <tr><td>Alma Linux 9</td><td>✅</td></tr>
        <tr><td colspan=2><a href="https://www.raspberrypi-spy.co.uk/2014/11/enabling-the-i2c-interface-on-the-raspberry-pi/">*Users of Raspberry Pi OS<br>should enable i2c manually*</td></tr>
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

- [Raspberry Pi Docs](https://www.raspberrypi.com/documentation)
- [Docker Docs](https://docs.docker.com/)
- [Docker Buildx Docs](https://docs.docker.com/buildx/working-with-buildx/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Ubuntu Server Docs](https://ubuntu.com/server/docs)
- [NGINX Docs](https://nginx.org/en/docs/)
- [React Docs](https://reactjs.org/docs/getting-started.html)
- [Node.js Docs](https://nodejs.org/en/docs/)
- [npm Docs](https://docs.npmjs.com/)

</td>
<td>

- [GPIO Pinout](https://www.raspberrypi.com/documentation/computers/images/GPIO-Pinout-Diagram-2.png)
- [luma.oled Docs](https://luma-oled.readthedocs.io/en/latest/)
- [pyttsx3 Docs](https://pypi.org/project/pyttsx3/)
- [I2C Docs](https://i2c.readthedocs.io/en/latest/)
- [ALSA Docs](https://www.alsa-project.org/wiki/Documentation)
- [PortAudio Docs](http://www.portaudio.com/docs/v19-doxydocs/index.html)
- [SpeechRecognition Docs](https://pypi.org/project/SpeechRecognition/)
- [OpenAI API Docs](https://platform.openai.com/docs/introduction)
- [CalDAV API Docs](https://caldav.readthedocs.io/en/latest/)
- [LiteLLM Docs](https://docs.litellm.ai/docs/)
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [LangMem Docs](https://langchain-ai.github.io/langmem/)

</td>
<td>

- [Spotify API Docs](https://developer.spotify.com/documentation/web-api/)
- [Spotify API Python Docs (Spotipy)](https://spotipy.readthedocs.io/)
- [Spotifyd Docs](https://docs.spotifyd.rs/)
- [Phillips Hue API Docs](https://developers.meethue.com/develop/get-started-2/)
- [Phillips Hue Python API Docs](https://github.com/studioimaginaire/phue)
- [OpenWeatherMap API Docs](https://openweathermap.org/api/one-call-3)
- [Open-Meteo API Docs](https://open-meteo.com/en/docs)
- [Python Crontab Docs](https://pypi.org/project/python-crontab/)
- [Fritzing Schematics](https://fritzing.org/)

</td>
</tr>
</table>

---

## 🤝 Contributing
Contributions are certainly welcome! Please read the [`contributing guidelines`](CONTRIBUTING.md) for more information on how to contribute.

## 📜 License
This project is licensed under the GNU GPL v3.0 License - see the [`LICENSE`](LICENSE) file for details.

## 🌟 Star History  
[![Star History Chart](https://api.star-history.com/svg?repos=judahpaul16/gpt-home&type=Date&theme=dark)](https://star-history.com/#judahpaul16/gpt-home)
