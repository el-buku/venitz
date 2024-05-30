from __future__ import print_function

import socket
import struct
import threading
from queue import LifoQueue

import cv2
from ffpyplayer.player import MediaPlayer

# Define the paths to the video files
video_paths = [
    "vid/windows-shut.mp4",  # Background video
    "vid/daniela.mp4",
    "vid/nicolo.mp4",
    "vid/rossanna.mp4",
    "vid/yvone.mp4",
]

# Define to 1 to use builtin "uwebsocket" module of MicroPython
USE_BUILTIN_UWEBSOCKET = 0
# Treat this remote directory as a root for file transfers
SANDBOX = ""
# SANDBOX = "/tmp/webrepl/"
DEBUG = 0

WEBREPL_REQ_S = "<2sBBQLH64s"
WEBREPL_PUT_FILE = 1
WEBREPL_GET_FILE = 2
WEBREPL_GET_VER = 3
WEBREPL_FRAME_TXT = 0x81
WEBREPL_FRAME_BIN = 0x82

is_playing = False


# Function to play video and audio using ffpyplayer
def play_video_with_audio(cap, player, q, loop=False, should_break=False):
    global is_playing
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            if loop:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                player.seek(0, relative=True)
                continue
            else:
                break

        # Sync the audio with the video frame
        audio_frame, val = player.get_frame()
        if val != "eof" and audio_frame is not None:
            img, t = audio_frame

        cv2.imshow("Video Player", frame)

        # Check for key press with a timeout of 1 ms
        key = cv2.waitKey(1)
        if key & 0xFF == ord("q"):
            cap.release()
            cv2.destroyAllWindows()
            return "quit"

        # Periodically check the queue for new index
        if not q.empty() and should_break:
            new_index = q.get()
            cap.release()
            return new_index

    cap.release()
    return None


# Simplified WebSocket class
class websocket:
    def __init__(self, s):
        self.s = s
        self.buf = b""

    def write(self, data, frame=WEBREPL_FRAME_BIN):
        l = len(data)
        if l < 126:
            hdr = struct.pack(">BB", frame, l)
        else:
            hdr = struct.pack(">BBH", frame, 126, l)
        self.s.send(hdr)
        self.s.send(data)

    def recvexactly(self, sz):
        res = b""
        while sz:
            data = self.s.recv(sz)
            if not data:
                break
            res += data
            sz -= len(data)
        return res

    def read(self, size, text_ok=False):
        if not self.buf:
            while True:
                hdr = self.recvexactly(2)
                assert len(hdr) == 2
                fl, sz = struct.unpack(">BB", hdr)
                if sz == 126:
                    hdr = self.recvexactly(2)
                    assert len(hdr) == 2
                    (sz,) = struct.unpack(">H", hdr)
                if fl == 0x82:
                    break
                if text_ok and fl == 0x81:
                    break
                while sz:
                    skip = self.s.recv(sz)
                    sz -= len(skip)
            data = self.recvexactly(sz)
            assert len(data) == sz
            self.buf = data

        d = self.buf[:size]
        self.buf = self.buf[size:]
        assert len(d) == size, len(d)
        return d

    def ioctl(self, req, val):
        assert req == 9 and val == 2


# Simplified client handshake for WebSocket
def client_handshake(sock):
    cl = sock.makefile("rwb", 0)
    cl.write(
        b"""\
GET / HTTP/1.1\r
Host: 192.168.4.1\r
Connection: Upgrade\r
Upgrade: websocket\r
Sec-WebSocket-Key: foo\r
\r
"""
    )
    l = cl.readline()
    while True:
        l = cl.readline()
        if l == b"\r\n":
            break


# Function to log in to the WebSocket server
def login(ws, passwd):
    while True:
        c = ws.read(1, text_ok=True)
        if c == b":":
            assert ws.read(1, text_ok=True) == b" "
            break
    ws.write(passwd.encode("utf-8") + b"\r")


# Function to handle WebSocket messages
def websocket_handler(ws, q):
    global is_playing
    line = ""
    while True:
        c = ws.read(1, text_ok=True)
        if c:
            char = c.decode()
            line += char
            if char.startswith("\n"):
                if not is_playing:  # Only update the queue if not playing
                    splitline = line.split(":")
                    if len(splitline) > 1:
                        new_index = splitline[1].strip()
                        q.put(new_index)
                line = ""


def debugmsg(msg):
    if DEBUG:
        print(msg)


def send_req(ws, op, sz=0, fname=b""):
    rec = struct.pack(WEBREPL_REQ_S, b"WA", op, 0, 0, sz, len(fname), fname)
    debugmsg("%r %d" % (rec, len(rec)))
    ws.write(rec)


def get_ver(ws):
    send_req(ws, WEBREPL_GET_VER)
    d = ws.read(3)
    d = struct.unpack("<BBB", d)
    return d


# Main loop
def main():
    global is_playing
    passwd = "repl"
    host = "192.168.4.1"
    port = 8266

    s = socket.socket()
    s.connect((host, port))
    client_handshake(s)

    ws = websocket(s)
    login(ws, passwd)

    print("repl:is_connected:", get_ver(ws))

    ws.ioctl(9, 2)

    # Create a queue for communication between threads
    q = LifoQueue()

    # Start the WebSocket handler thread
    threading.Thread(target=websocket_handler, args=(ws, q), daemon=True).start()

    bg_vid = video_paths[0]
    player = MediaPlayer(bg_vid)
    cap = cv2.VideoCapture(bg_vid)
    import time

    while True:
        time.sleep(0.01)
        # print("is_playing", is_playing)
        if not is_playing:
            try:
                new_vid = q.get_nowait()
                print("newq", new_vid)
                video_path = video_paths[int(new_vid)]
                print(video_path)
                is_playing = True
                cap.open(video_path)
                player = MediaPlayer(video_path)
                result = play_video_with_audio(cap, player, q, False, False)
                # time.sleep(1)
                is_playing = False

            except:
                play_video_with_audio(cap, player, q, True, True)

    cap.release()
    cv2.destroyAllWindows()
    s.close()


if __name__ == "__main__":
    main()
