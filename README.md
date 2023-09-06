# ChatGPT Home
ChatGPT at home! Basically a better G**gle Nest Hub made with Raspberry Pi and OpenAI.

## Example Reclone script:
``` bash
    #!/bin/bash

    # Initialize environment variables
    export OPENAI_API_KEY="your_openai_api_key_here"
    export DEPENDENCIES_INSTALLED="false"

    # Install dependencies if not installed
    if [ "$DEPENDENCIES_INSTALLED" == "false" ]; then
        sudo apt-get update
        sudo apt-get install -y python3-pip
        sudo apt-get install -y portaudio19-dev python3-pyaudio
        export DEPENDENCIES_INSTALLED="true"
    fi

    # Remove existing repo if it exists
    if [ -d "chatgpt-home" ]; then
        rm -rf chatgpt-home
    fi

    # Clone the GitHub repo
    git clone https://github.com/judahpaul16/chatgpt-home.git

    # Navigate to directory containing the Python script
    cd chatgpt-home

    # Install Python dependencies
    pip3 install -r requirements.txt

    # Run Python script
    python3 app.py
```
Be sure to make the script executable to run it
```bash
    chmod +x reclone.sh
    ./reclone.sh
```

## Example Systemd Service:
```bash
    [Unit]
    Description=ChatGPT Home
    After=network.target

    [Service]
    User=pi
    WorkingDirectory=/home/pi/chatgpt-home
    ExecStart=/home/pi/chatgpt-home/reclone.sh
    Restart=always

    [Install]
    WantedBy=multi-user.target
```
Enable the service
```bash
    sudo systemctl enable chatgpt-home.service
```
Start the service
```bash
    sudo systemctl start chatgpt-home.service
```

## Documentation
[OpenAI API Docs](https://beta.openai.com/docs/introduction)
<br>
[SpeechRecognition Docs](https://pypi.org/project/SpeechRecognition/)
<br>
[pyttsx3 Docs](https://pypi.org/project/pyttsx3/)
<br>
[Requests Docs](https://pypi.org/project/requests/)
<br>
[PortAudio Docs](http://www.portaudio.com/docs/v19-doxydocs/index.html)
<br>
[Python3 Docs](https://docs.python.org/3/)
<br>
