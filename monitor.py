#!/usr/bin/env python3

import evdev
import pyudev
import os
import sys
import glob
import uinput
import argparse
import subprocess
import select
import threading
import time


DEBUG = True


# Lista de dispositivos conhecidos
DEVICE_IDS = [
    {"VENDOR_ID": 0xABC8, "PRODUCT_ID": 0xCA08, "CLASS": "BaseusOrangeDotAI"},
    # Adicione outros pares vendor/product aqui
]

event_thread = None  # Global para controlar a thread de bloqueio
monitored_devices = set()


class AppContext:
    def __init__(self, spx_proc=None, screen=0, uid=None):
        self._spx_proc = spx_proc
        self._selected_screen = screen
        self._ui = uid

    @property
    def ui(self):
        return self._ui

    @ui.setter
    def ui(self, uid):
        self._ui = uid

    @property
    def spx_proc(self):
        return self._spx_proc

    @spx_proc.setter
    def spx_proc(self, spxc):
        self._spx_proc = spxc

    @property
    def selected_screen(self):
        return self._selected_screen

    @selected_screen.setter
    def selected_screen(self, scr):
        self._selected_screen = scr


def start_spx_proc(ctx):
    if ctx.spx_proc is None or ctx.spx_proc.poll() is not None:
        print("🚀 Iniciando spx.py")
        ctx.spx_proc = subprocess.Popen(
            get_spx_cmd(ctx),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def read_spx_output(proc):
            for line in proc.stdout:
                print(f"[spx] {line.strip()}")
            for line in proc.stderr:
                print(f"[E: spx] {line.strip()}")

        threading.Thread(
            target=read_spx_output, args=(ctx.spx_proc,), daemon=True
        ).start()


def get_spx_cmd(ctx):
    current_script_path = os.path.dirname(os.path.abspath(__file__))
    spx_cmd = [
        sys.executable,
        os.path.join(current_script_path, "spx.py"),
        str(ctx.selected_screen),
    ]
    return spx_cmd


def is_known_device(hidraw_path):
    try:
        output = subprocess.check_output(
            ["udevadm", "info", "-a", "-n", hidraw_path], text=True
        ).lower()
        for dev in DEVICE_IDS:
            vid = f"{dev['VENDOR_ID']:04x}"
            pid = f"{dev['PRODUCT_ID']:04x}"
            if vid in output and pid in output:
                return True, dev
        return False, None
    except subprocess.CalledProcessError:
        return False, None


def find_known_hidraws():
    devices = []
    for path in glob.glob("/dev/hidraw*"):
        ok, dev_info = is_known_device(path)
        if ok:
            devices.append((path, dev_info))
    return devices


def find_evdev_path_from_hidraw(hidraw_path):
    # Mapeia /dev/hidrawX para /dev/input/eventX
    try:
        base_name = os.path.basename(hidraw_path)
        sys_path = f"/sys/class/hidraw/{base_name}/device"
        input_base = os.path.join(sys_path, "input")
        inputs = os.listdir(input_base)
        if not inputs:
            return None
        input_path = os.path.join(input_base, inputs[0])
        event_devices = [f for f in os.listdir(input_path) if f.startswith("event")]
        if not event_devices:
            return None
        event_path = os.path.join("/dev/input", event_devices[0])
        return event_path
    except Exception:
        return None


def is_known_event_device(path):
    try:
        output = subprocess.check_output(
            ["udevadm", "info", "-a", "-n", path], text=True
        ).lower()
        for dev in DEVICE_IDS:
            vid = f"{dev['VENDOR_ID']:04x}"
            pid = f"{dev['PRODUCT_ID']:04x}"
            if vid in output and pid in output:
                return True
    except Exception as e:
        print(f"⚠️ Erro ao verificar {path}: {e}")
    return False


def find_all_event_devices_for_known():
    devices = []
    for path in glob.glob("/dev/input/event*"):
        if is_known_event_device(path):
            try:
                devices.append(evdev.InputDevice(path))
                print(f"🟢 Encontrado device de entrada: {path}")
            except Exception as e:
                print(f"⚠️ Erro ao acessar {path}: {e}")
    return devices


def hotplug_callback(action, device, ctx):
    global event_thread

    path = device.device_node
    if not path:
        return

    if action == "add":
        if path.startswith("/dev/hidraw"):
            if path in monitored_devices:
                return  # já monitorado
            ok, dev_info = is_known_device(path)
            if ok:
                print(f"➕ Novo dispositivo HID compatível conectado: {path}")
                cls = globals()[dev_info["CLASS"]]
                dev = cls(path, app_ctx=ctx)
                t = threading.Thread(target=dev.monitor, daemon=True)
                t.start()
                monitored_devices.add(path)

        elif path.startswith("/dev/input/event"):
            if is_known_event_device(path):
                print(f"🆕 Dispositivo de entrada compatível conectado: {path}")
                # Reinicia o bloqueio de eventos se necessário
                if not event_thread or not event_thread.is_alive():
                    devs = find_all_event_devices_for_known()
                    if devs:
                        event_thread = threading.Thread(
                            target=prevent_key_and_mouse_events,
                            args=(devs, ctx),
                            daemon=True,
                        )
                        event_thread.start()

    elif action == "remove":
        if path in monitored_devices:
            print(f"➖ Dispositivo HID removido: {path}")
            monitored_devices.remove(path)
            # Encerra o processo spx.py se estiver rodando
            if ctx.spx_proc and ctx.spx_proc.poll() is None:
                print("⏹️ Encerrando processo spx.py após remoção de dispositivo.")
                try:
                    ctx.spx_proc.terminate()
                    ctx.spx_proc.wait(timeout=2)
                except Exception as e:
                    print(f"⚠️ Erro ao encerrar spx.py: {e}")
                finally:
                    ctx.spx_proc = None


def monitor_usb_hotplug(ctx):
    def monitor_loop():
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by("hidraw")
        monitor.start()

        for device in iter(monitor.poll, None):
            action = device.action  # 'add' ou 'remove'
            hotplug_callback(action, device, ctx)

    threading.Thread(target=monitor_loop, daemon=True).start()


class BasePointerDevice:
    def __init__(self, path, app_ctx):
        self.path = path
        self.ctx = app_ctx
        self.last_click_time_113 = 0
        self.double_click_interval = 0.3  # segundos para considerar duplo clique

    def monitor(self):
        try:
            with open(self.path, "rb") as f:
                for pacote in self.read_pacotes_completos(f):
                    self.processa_pacote_hid(pacote)
        except PermissionError:
            print(
                f"🚫 Sem permissão para acessar {self.path} (tente ajustar udev ou rodar com sudo)"
            )
        except KeyboardInterrupt:
            print(f"\nFinalizando monitoramento de {self.path}")
        except OSError as e:
            if e.errno == 5:  # Input/output error
                print("Dispositivo desconectado ou erro de I/O")
            else:
                print(f"⚠️ Erro em {self.path}: {e}")

        except Exception as e:
            print(f"⚠️ Erro em {self.path}: {e}")

    def send_spx_command(self, command, log_msg=None):
        proc = self.ctx.spx_proc

        if proc is None or proc.poll() is not None:
            # Processo já terminou — evitar enviar e limpar
            self.ctx.spx_proc = None
            print(f"⚠️ Processo spx.py finalizado. Ignorando comando: {command}")
            return

        try:
            if log_msg:
                print(log_msg)
            proc.stdin.write(f"{command}\n")
            proc.stdin.flush()
        except BrokenPipeError:
            print(f"⚠️ Broken pipe ao enviar comando '{command}' — processo finalizado.")
            self.ctx.spx_proc = None
        except Exception as e:
            print(f"Erro ao enviar comando '{command}': {e}")


def emit_key_press(ui, key):
    ui.emit(key, 1)  # Pressiona
    ui.emit(key, 0)  # Solta


def emit_key_chord(ui, keys):
    ui.emit(keys[0], 1)  # Pressiona primeira tecla, ex: SHIFT
    ui.emit(keys[1], 1)  # Pressiona segunda tecla ex: F5
    ui.emit(keys[1], 0)  # Solta segunda tecla
    ui.emit(keys[0], 0)  # Solta primeira tecla


class BaseusOrangeDotAI(BasePointerDevice):
    def read_pacotes_completos(self, f):
        buffer = bytearray()
        while True:
            b = f.read(1)
            if not b:
                break
            buffer += b
            if b[0] == 182:
                yield bytes(buffer)
                buffer.clear()

    def processa_pacote_hid(self, data):
        if not (
            isinstance(data, bytes)
            and len(data) == 16
            and data[0] == 10
            and data[-1] == 182
        ):
            return

        status_byte = data[5]
        if status_byte == 0:
            return

        command = None
        spx_is_not_running = (
            self.ctx.spx_proc is None or self.ctx.spx_proc.poll() is not None
        )

        match status_byte:
            case 97:
                if spx_is_not_running:
                    emit_key_press(self.ctx.ui, uinput.BTN_LEFT)
            case 99:
                if spx_is_not_running:
                    start_spx_proc(self.ctx)
            case 103:
                command = "clear_drawing"
            case 104 | 114:
                command = "start_move"
            case 105 | 115:
                command = "stop_move"
            case 106:
                if spx_is_not_running:
                    emit_key_press(self.ctx.ui, uinput.KEY_PAGEUP)
                else:
                    command = "decrease_size"
            case 107:
                if spx_is_not_running:
                    emit_key_press(self.ctx.ui, uinput.KEY_ESC)
                else:
                    command = "quit_spx"
            case 108:
                if spx_is_not_running:
                    emit_key_press(self.ctx.ui, uinput.KEY_PAGEDOWN)
                else:
                    command = "increase_size"
            case 109:
                if spx_is_not_running:
                    emit_key_chord(self.ctx.ui, [uinput.KEY_LEFTSHIFT, uinput.KEY_F5])
            case 113:
                now = time.time()
                if now - self.last_click_time_113 < self.double_click_interval:
                    if spx_is_not_running:
                        start_spx_proc(self.ctx)
                        # Aguarda brevemente para garantir que o processo esteja pronto
                        time.sleep(0.1)
                    else:
                        command = "next_mode"
                self.last_click_time_113 = now
            case 116 | 117:
                command = "color_next"
            case 120:
                if spx_is_not_running:
                    emit_key_press(self.ctx.ui, uinput.KEY_VOLUMEUP)
                else:
                    command = "zoom_in"
            case 121:
                if spx_is_not_running:
                    emit_key_press(self.ctx.ui, uinput.KEY_VOLUMEDOWN)
                else:
                    command = "zoom_out"
            case 122 | 123:
                command = "color_prior"

        if command and not spx_is_not_running:
            print(f"send command: {command}")
            self.send_spx_command(command)


def prevent_key_and_mouse_events(dispositivos, ctx):
    fd_para_dev = {}
    for dev in dispositivos:
        try:
            dev.grab()
            fd_para_dev[dev.fd] = dev
            print(f"🟢 Grabbed: {dev.path}")
        except Exception as e:
            print(f"❌ Erro ao grab {dev.path}: {e}")

    print("🟢 Monitorando dispositivos...")

    ctx.ui = uinput.Device(
        [
            uinput.REL_X,
            uinput.REL_Y,
            uinput.BTN_LEFT,
            uinput.BTN_RIGHT,
            uinput.KEY_B,
            uinput.KEY_PAGEUP,
            uinput.KEY_PAGEDOWN,
            uinput.KEY_ESC,
            # uinput.KEY_LEFTCTRL,
            uinput.KEY_F5,
            uinput.KEY_SPACE,
            uinput.KEY_LEFTSHIFT,
            uinput.KEY_VOLUMEUP,
            uinput.KEY_VOLUMEDOWN,
        ],
        name="Virtual Spotlight Mouse",
    )

    try:
        while True:
            r, _, _ = select.select(fd_para_dev, [], [])
            for fd in r:
                dev = fd_para_dev.get(fd)
                if dev is None:
                    continue
                try:
                    for event in dev.read():
                        if event.type == evdev.ecodes.EV_REL or (
                            event.type == evdev.ecodes.EV_KEY
                            and event.code
                            in (
                                evdev.ecodes.BTN_LEFT,
                                evdev.ecodes.BTN_RIGHT,
                            )
                        ):
                            # Repassa evento virtual
                            ctx.ui.emit((event.type, event.code), event.value)

                except OSError as e:
                    if e.errno == 19:  # No such device
                        print(f"⚠️ Dispositivo desconectado: {dev.path}")
                        # Remove dispositivo da lista para não monitorar mais
                        fd_para_dev.pop(fd, None)
                        try:
                            dev.ungrab()
                        except Exception:
                            pass
                        # Opcional: se não há mais dispositivos, pode encerrar ou esperar
                        if not fd_para_dev:
                            print(
                                "Nenhum dispositivo restante para monitorar. Encerrando thread."
                            )
                            return
                    else:
                        raise

    except KeyboardInterrupt:
        print("\n⏹️ Encerrando monitoramento.")
    finally:
        for dev in dispositivos:
            try:
                dev.ungrab()
            except Exception:
                pass
        if ctx.spx_proc and ctx.spx_proc.poll() is None:
            ctx.spx_proc.terminate()


def main():
    parser = argparse.ArgumentParser(
        description="Monitor de HID e Mouse para Spotlight"
    )
    parser.add_argument(
        "-s", "--screen", type=int, default=0, help="Número da tela (default=0)"
    )
    args = parser.parse_args()

    ctx = AppContext(screen=args.screen)

    # Inicia monitoramento hotplug (funcionará mesmo sem dispositivos)
    monitor_usb_hotplug(ctx)

    # Encontra e inicia monitoramento de dispositivos já conectados
    hidraws = find_known_hidraws()
    if hidraws:
        for path, dev_info in hidraws:
            cls = globals()[dev_info["CLASS"]]
            dev = cls(path, app_ctx=ctx)
            threading.Thread(target=dev.monitor, daemon=True).start()
    else:
        print(
            "⚠️ Nenhum dispositivo compatível encontrado no início. Aguardando conexão..."
        )

    dispositivos_para_bloquear = find_all_event_devices_for_known()
    if dispositivos_para_bloquear:
        t = threading.Thread(
            target=prevent_key_and_mouse_events,
            args=(dispositivos_para_bloquear, ctx),
            daemon=True,
        )
        t.start()
    else:
        print("❌ Nenhum dispositivo para bloquear.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Encerrando monitoramento de dispositivos HID.")


if __name__ == "__main__":
    main()
