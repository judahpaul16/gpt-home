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
    ```bash
    sudo vim /etc/rc.local
    ```
    Add the following line:
    ```bash
    sudo ifconfig wlan0 up
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

5. Restart `wpa_supplicant` service:
    ```bash
    sudo systemctl restart wpa_supplicant.service
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

1. **Python 3.x**: Required for running the Python code.  
   Installation: `sudo apt-get install python3`

2. **Python Development Headers**: Required for building certain Python packages.  
   Installation: `sudo apt-get install python3.11-dev`

3. **PortAudio**: Required for `pyttsx3` (text-to-speech).  
   Installation: `sudo apt-get install portaudio19-dev`

4. **ALSA Utilities**: Required for audio configuration.  
   Installation: `sudo apt-get install alsa-utils`

5. **JPEG Library**: Required for Pillow.  
   Installation: `sudo apt-get install libjpeg-dev`

6. **Build Essentials**: Required for building packages.  
   Installation: `sudo apt-get install build-essential`

7. **vcgencmd**: Comes pre-installed on Raspberry Pi OS. Used for fetching CPU temperature.

8. **Speech Recognition Libraries**: Required for `speech_recognition`.  
   Installation: `sudo apt-get install libasound2-dev`

9. **I2C Support**: Required for `adafruit_ssd1306` (OLED display).  
   Enable via `raspi-config` or install packages:  
   ```
   sudo apt-get install -y i2c-tools
   sudo apt-get install -y python3-smbus
   ```

10. **Git**: Required for cloning the repository.  
    Installation: `sudo apt-get install git`

11. **OpenAI API Key**: Required for OpenAI's GPT API.  
    Setup: Set up as an environment variable.  

12. **eSpeak Library**: Required for text-to-speech (`pyttsx3`).  
   Installation: `sudo apt-get install libespeak1`

### Optional Dependencies

1. **Virtual Environment**: Recommended for Python package management.  
   Installation: `sudo apt-get install python3-venv`

---

## 📜 Example Reclone script:
First initialize an environment variable with your OpenAI API Key.
```bash
export OPENAI_API_KEY="your_openai_api_key_here"
```
Then create a script outside the local repo folder to reclone the repo and start the service.
```bash
#!/bin/bash

# Remove existing local repo if it exists
if [ -d "gpt-home" ]; then
    rm -rf gpt-home
fi

# Clone the GitHub repo
git clone https://github.com/judahpaul16/gpt-home.git

# Navigate to root of the local repo
cd gpt-home

# Create a virtual environment
python3 -m venv env

# Activate the virtual environment
source env/bin/activate

# Upgrade pip
pip install --upgrade pip

# Upgrade setuptools
pip install --upgrade setuptools

# Install Python dependencies
pip install --use-pep517 -r requirements.txt

# Define the name of the systemd service
SERVICE_NAME="gpt-home.service"

# Check if the systemd service already exists, recreate it if it does
if [ -f "/etc/systemd/system/$SERVICE_NAME" ]; then
    sudo systemctl stop "$SERVICE_NAME"
fi

echo "Creating and enabling systemd service $SERVICE_NAME..."

# Create a systemd service unit file
cat <<EOF | sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null
[Unit]
Description=GPT Home
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/gpt-home
ExecStart=/home/ubuntu/gpt-home/env/bin/python /home/ubuntu/gpt-home/app.py
Environment="OPENAI_API_KEY=$OPENAI_API_KEY"
Restart=always
Type=simple

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable the service
sudo systemctl enable "$SERVICE_NAME"

echo "Systemd service $SERVICE_NAME created and enabled."

# Start the service
sudo systemctl restart "$SERVICE_NAME"
echo ""
sleep 3
sudo systemctl status "$SERVICE_NAME"
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
