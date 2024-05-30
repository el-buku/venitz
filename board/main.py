import socket
import time

import machine
import ure

# Define the GPIO pins for video selection
video_pins = [
    machine.Pin(14, machine.Pin.IN, machine.Pin.PULL_UP),  # Pin for video 1
    machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_UP),  # Pin for video 2
    machine.Pin(13, machine.Pin.IN, machine.Pin.PULL_UP),  # Pin for video 3
    machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_UP),  # Pin for video 5
    machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP),  # Pin for video 6
]

# Log file for key presses
KEY_PRESS_LOG = "keypresses.dat"


# Function to log key presses with timestamps
def log_key_press(video_index):
    timestamp = time.time()
    with open(KEY_PRESS_LOG, "a") as log_file:
        log_file.write(f"{timestamp},{video_index}\n")


# Function to get the latest valid key press
def get_latest_key_press():
    try:
        with open(KEY_PRESS_LOG, "r") as log_file:
            lines = log_file.readlines()
            if lines:
                return lines[-1].strip()
    except OSError:
        pass
    return "No key press recorded."


# Function to send the latest key press
def handle_pressed(client):
    latest_key_press = get_latest_key_press()
    send_response(client, latest_key_press)


def send_header(client, status_code=200, content_length=None):
    client.sendall("HTTP/1.0 {} OK\r\n".format(status_code))
    client.sendall("Content-Type: text/html\r\n")
    if content_length is not None:
        client.sendall("Content-Length: {}\r\n".format(content_length))
    client.sendall("\r\n")


def send_response(client, payload, status_code=200):
    content_length = len(payload)
    send_header(client, status_code, content_length)
    if content_length > 0:
        client.sendall(payload.encode())  # Encode the payload as bytes
    client.close()


def start(port=80):
    addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
    server_socket = socket.socket()
    server_socket.bind(addr)
    server_socket.listen(1)

    print("Server listening on:", addr)

    client, addr = server_socket.accept()
    print("Client connected from", addr)
    try:
        client.settimeout(5.0)
        request = b""
        try:
            while "\r\n\r\n" not in request:
                request += client.recv(512)
        except OSError:
            pass

        print("Request is: {}".format(request))
        if "HTTP" not in request:  # skip invalid requests
            return

        url = ure.search(r"(?:GET|POST) /(.*?)(?:\?.*?)? HTTP", request.decode())
        if url:
            url = url.group(1).rstrip("/")
        else:
            url = ""
        print("URL is {}".format(url))

        handle_pressed(client)

    finally:
        client.close()


def handle_not_found(client, url):
    send_response(client, "Path not found: {}".format(url), status_code=404)


def server_thread():
    start(port=80)


def gpio_thread():
    # Main loop to check GPIO pins
    led_pin = machine.Pin(2, machine.Pin.OUT)  # GPIO 2
    led_pin.off()
    for i, pin in enumerate(video_pins, start=1):
        if pin() == 0:
            start_time = time.time()
            while pin() == 0:
                if time.time() - start_time >= 1:  # Check if held for 1 second
                    video_index = i
                    led_pin.on()
                    log_key_press(video_index)
                    print(f"Logged video index: {video_index}")
                    break
            time.sleep(0.05)
        else:
            print("idle.")
            time.sleep(0.05)


while True:
    # server_thread()
    gpio_thread()
