import evdev
from select import select

devices = [
    evdev.InputDevice(path)
    for path in [
        "/dev/input/event22",
        "/dev/input/event23",
        "/dev/input/event24",
        "/dev/input/event25",
    ]
]

# Mostra nomes dos dispositivos
for dev in devices:
    print(f"{dev.path}: {dev.name}")

# Prepara os file descriptors para polling
device_fds = {dev.fd: dev for dev in devices}

while True:
    r, _, _ = select(device_fds.keys(), [], [])
    for fd in r:
        for event in device_fds[fd].read():
            if event.type == evdev.ecodes.EV_KEY or event.type == evdev.ecodes.EV_REL:
                print(evdev.categorize(event))
