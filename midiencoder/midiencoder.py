import mido
import subprocess
import time
import threading

# Available MIDI input ports:
# 0: 3- Delta 1010LT MIDI 0
# 1: ...
# 2: 3- BCR2000 port 1 1
# 3: 3- BCR2000 port 2 2
# 4: 3- BCR2000 port 3 3

MIDI_PORT = "3- Delta 1010LT MIDI 0"
CC = 90

MIN_VALUE = 600
MAX_VALUE = 1300

CMD_FILE = r"C:\Projects\python\midiencoder\darkambient-mplayer.bat"

# Currently running CMD process
current_process = None

# Timer used to wait for encoder movement to stop
start_timer = None

# Protect shared variables
lock = threading.Lock()


def map_value(value):
    return round(
        MIN_VALUE +
        (value / 127.0) * (MAX_VALUE - MIN_VALUE)
    )


def terminate_previous_process():
    global current_process

    if current_process is not None:
        if current_process.poll() is None:
            print("Terminating previous CMD process...")

            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(current_process.pid),
                    "/T",
                    "/F"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        current_process = None


def start_cmd(value):
    global current_process

    with lock:
        # Stop previous CMD process
        terminate_previous_process()

        # Start new CMD process
        current_process = subprocess.Popen(
            [CMD_FILE, str(value)],
            shell=False
        )

        print(
            f"Started CMD process: "
            f"PID={current_process.pid}, value={value}"
        )


def delayed_start(value):
    """
    Called 1 second after the last MIDI CC.
    """
    print(f"1 second elapsed - starting CMD with value {value}")
    start_cmd(value)


def schedule_cmd(value):
    global start_timer

    with lock:
        # Cancel previous timer
        if start_timer is not None:
            start_timer.cancel()

        # Start/restart 1-second timer
        start_timer = threading.Timer(
            1.0,
            delayed_start,
            args=(value,)
        )

        start_timer.daemon = True
        start_timer.start()


print("Available MIDI ports:")

for port in mido.get_input_names():
    print("  ", port)

print("\nOpening:", MIDI_PORT)

with mido.open_input(MIDI_PORT) as port:

    for msg in port:

        if msg.type == "control_change" and msg.control == CC:

            midi_value = msg.value
            value = map_value(midi_value)

            print(
                f"CC {CC}: {midi_value} -> {value} "
                f"(waiting 1 second...)"
            )

            # Do NOT start CMD immediately.
            # Wait until 1 second has passed without
            # receiving another CC.
            schedule_cmd(value)