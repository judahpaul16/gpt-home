
from board import SCL, SDA
import busio
import adafruit_ssd1306
import subprocess

def initLCD():
    # Create the I2C interface.
    i2c = busio.I2C(SCL, SDA)

    # Create the SSD1306 OLED class.
    # The first two parameters are the pixel width and pixel height. Change these
    # to the right size for your display!
    display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
    # Alternatively, you can change the I2C address of the device with an addr parameter:
    # display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, addr=0x31)

    # Set the display rotation to 180 degrees.
    display.rotation = 2

    # Clear the display. Always call show after changing pixels to make the display
    # update visible!
    display.fill(0)

    display.show()

    # Display IP address
    ip_address = (
        subprocess.check_output(["hostname", "-I"])
        .decode("utf-8")
        .split(" ")[0]
    )
    display.text("IP: " + str(ip_address), 0, 0, 1)

    # Show the updated display with the text.
    display.show()
    return display

def updateLCD(text, display):
    display.fill(0)
    ip_address = (
        subprocess.check_output(["hostname", "-I"])
        .decode("utf-8")
        .split(" ")[0]
    )
    display.text("IP: " + str(ip_address), 0, 0, 1)
    # next row if text is too long
    if len(text) > 21:
        if len(text) > 42:
            # scroll text
            display.text(text[:21], 0, 10, 1)
            display.text(text[21:42], 0, 20, 1)
            display.text(text[42:], 0, 30, 1)
        else:
            # split into two lines
            display.text(text[:21], 0, 10, 1)
            display.text(text[21:], 0, 20, 1)
    else:
        display.text(text, 0, 10, 1)
    display.show()

def speak(text, engine):
    engine.say(text)
    engine.runAndWait()