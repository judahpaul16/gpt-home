# 🏠 GPT Home
GPT at home! Basically a better G**gle Nest Hub desk assistant made with Raspberry Pi and OpenAI API.

* *This guide assumes you're using Ubuntu Server as your Raspberry Pi operating system. You may need to make certain modifications to accomodate other operating systems*

## 📶 Configuring Wi-Fi via wpa_supplicant

To configure Wi-Fi on your Raspberry Pi, you'll need to edit the `wpa_supplicant.conf` file and ensure the wireless interface is enabled at boot.

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
    ```
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

Before running this project on your Raspberry Pi, you'll need to install some system-level dependencies in addition to the Python packages.

1. Update your package list:
    ```bash
    sudo apt update
    ```

2. Make sure the Universe repository is enabled:
    ```bash
    sudo add-apt-repository universe
    sudo apt update
    ```

### Required Dependencies

1. **OpenAI API Key**: Required for OpenAI's GPT API.  
    Setup: Set up as an environment variable.  

2. **Python 3.x**: Required for running the Python code.  
   Installation: `sudo apt-get install python3`

3. **Python Development Headers**: Required for building certain Python packages.  
   Installation: `sudo apt-get install python3.11-dev`

4. **PortAudio**: Required for `pyttsx3` (text-to-speech).  
   Installation: `sudo apt-get install portaudio19-dev`

5. **ALSA Utilities**: Required for audio configuration.  
   Installation: `sudo apt-get install alsa-utils`

6. **JPEG Library**: Required for Pillow.  
   Installation: `sudo apt-get install libjpeg-dev`

7. **Build Essentials**: Required for building packages.  
   Installation: `sudo apt-get install build-essential`

8. **vcgencmd**: Comes pre-installed on Raspberry Pi OS. Used for fetching CPU temperature.

9. **Speech Recognition Libraries**: Required for `speech_recognition`.  
   Installation: `sudo apt-get install libasound2-dev`

10. **I2C Support**: Required for `adafruit_ssd1306` (OLED display).  
   Enable via `raspi-config` or install packages:  
   ```
   sudo apt-get install -y i2c-tools
   sudo apt-get install -y python3-smbus
   ```

11. **eSpeak Library**: Required for text-to-speech (`pyttsx3`).  
   Installation: `sudo apt-get install libespeak1`

12. **JACK Audio Connection Kit**: Required for handling audio.  
   Installation: `sudo apt-get install jackd2`  
   Select `Yes` when prompted to enable realtime privileges.

13. **FLAC Libraries**: Required for handling FLAC audio formats.  
   Installation: `sudo apt-get install flac libflac12:armhf`

14. **Git**: Required for cloning the repository.  
    Installation: `sudo apt-get install git`

15. **Node.js and npm**: Required for the web interface.  
    Installation: [Follow NodeSource Installation Guide](https://github.com/nodesource/distributions#installation-instructions)

### Optional Dependencies

1. **Virtual Environment**: Recommended for Python package management.  
   Installation: `sudo apt-get install python3-venv`

---

## 📜 Example Reclone script:
First initialize an environment variable with your OpenAI API Key.
```bash
export OPENAI_API_KEY="your_openai_api_key_here"
```
Then create a script outside the local repo folder to reclone the repo and start the services.
```bash
#!/bin/bash

# Function to setup a systemd service
setup_service() {
    # Parameters
    local SERVICE_NAME=$1
    local EXEC_START=$2
    local AFTER=$3
    local ENV=$4
    local LMEMLOCK=$5

    # Stop the service if it's already running
    sudo systemctl stop "$SERVICE_NAME" &>/dev/null

    echo "Creating and enabling $SERVICE_NAME..."

    # Create systemd service file
    cat <<EOF | sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null
[Unit]
Description=$SERVICE_NAME
After=$AFTER
StartLimitIntervalSec=500
StartLimitBurst=10

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/gpt-home
ExecStart=$EXEC_START
$ENV
Restart=always
Type=simple
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

# Setup gpt-home service
setup_service "gpt-home.service" "/bin/bash -c 'source /home/ubuntu/gpt-home/env/bin/activate && python /home/ubuntu/gpt-home/app.py'" "" "Environment=\"OPENAI_API_KEY=$OPENAI_API_KEY\"" "LimitMEMLOCK=infinity"

## Setup Web Interface
# Navigate to web_interface and install dependencies
cd web_interface
npm install

# Build the React App
npm run build

# Setup web_interface service for React frontend
setup_service "web-interface.service" "npm start --prefix /home/ubuntu/gpt-home/web_interface" "" ""

# Setup fastapi service for FastAPI backend
setup_service "fastapi-service.service" "/bin/bash -c 'source /home/ubuntu/gpt-home/env/bin/activate && uvicorn src.backend:app --host 0.0.0.0 --port 8000'" "" ""
```
Be sure to make the script executable to run it
```bash
chmod +x reclone.sh
./reclone.sh
```
(Optional) .bashrc helpers<br>
**Put this at the end of your ~/.bashrc file**
```bash
# export your OpenAI API Key here to initialize it on login
export OPENAI_API_KEY="your_openai_api_key_here"

alias gpt-start="sudo systemctl start gpt-home"
alias gpt-restart="sudo systemctl restart gpt-home"
alias gpt-stop="sudo systemctl stop gpt-home"
alias gpt-disable="sudo systemctl disable gpt-home"
alias gpt-status="sudo systemctl status gpt-home"
alias gpt-enable="sudo systemctl enable gpt-home"
alias gpt-log="tail -n 100 -f /home/ubuntu/gpt-home/events.log"

alias web-start="sudo systemctl start web-interface && sudo systemctl start fastapi-service"
alias web-restart="sudo systemctl restart web-interface && sudo systemctl restart fastapi-service"
alias web-stop="sudo systemctl stop web-interface && sudo systemctl stop fastapi-service"
alias web-disable="sudo systemctl disable web-interface && sudo systemctl disable fastapi-service"
alias web-status="sudo systemctl status web-interface && sudo systemctl status fastapi-service"
alias web-enable="sudo systemctl enable web-interface && sudo systemctl enable fastapi-service"
alias web-log="tail -n 100 -f /home/ubuntu/gpt-home/web_interface/events.log"
```

---

## ⚠️ Schematics / Wiring Diagram
### Caution: Battery Connection
**IMPORTANT**: Before connecting the battery, ensure that the polarity is correct to avoid damage to your Raspberry Pi or other components. Disconnect power sources before making changes.

<table style="border-collapse: collapse; border: 0;">
  <tr>
    <td style="border: none;"><img src="schematic_bb.png" alt="Schematics Breadboard" height="350px" /></td>
    <td style="border: none;"><img src="schematic_schem.png" alt="Schematics Schematic" height="350px" /></td>
  </tr>
</table>
<span style="font-size: 1em; display:block;">[click to enlarge]</span>

---

## 📸 My Build
![My Build](my_build.jpg)
<span style="font-size: 1em; display:block;">[click to enlarge]</span>

---

## 🛠 My Parts List

### Core Components
- **Raspberry Pi 4B**: [Link](https://a.co/d/aH6YCXY) - $50-$70
- **Mini Speaker**: [Link](https://a.co/d/9bN8LZ2) - $18
- **128x32 OLED Display**: [Link](https://a.co/d/4Scrfjq) - $13-$14
- **128 GB MicroSD card**: [Link](https://a.co/d/0SxSg7O) - $13
- **USB 2.0 Mini Microphone**: [Link](https://a.co/d/eIrQUXC) - $8

---

### 🌟 Optional Components
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

## 📚 Useful Documentation
- [Raspberry Pi Docs](https://www.raspberrypi.com/documentation)
- [GPIO Pinout](https://www.raspberrypi.com/documentation/computers/images/GPIO-Pinout-Diagram-2.png)
- [OpenAI API Docs](https://beta.openai.com/docs/introduction)
- [SpeechRecognition Docs](https://pypi.org/project/SpeechRecognition/)
- [pyttsx3 Docs](https://pypi.org/project/pyttsx3/)
- [Requests Docs](https://pypi.org/project/requests/)
- [PortAudio Docs](http://www.portaudio.com/docs/v19-doxydocs/index.html)
- [Python3 Docs](https://docs.python.org/3/)
- [Fritzing Schematics](https://fritzing.org/)
