from abc import abstractmethod
from typing import Iterator


class BasePointerDevice:
    def __init__(self, path, app_ctx):
        self.path = path
        self.ctx = app_ctx
        self.last_click_time_113 = 0
        self.double_click_interval = 0.3  # segundos para considerar duplo clique

    @abstractmethod
    def read_pacotes_completos(self, f) -> Iterator:
        # Implement on device class
        pass

    @abstractmethod
    def processa_pacote_hid(self, data):
        # Implement on device class
        pass

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

    def emit_key_press(self, ui, key):
        ui.emit(key, 1)  # Pressiona
        ui.emit(key, 0)  # Solta

    def emit_key_chord(self, ui, keys):
        ui.emit(keys[0], 1)  # Pressiona primeira tecla, ex: SHIFT
        ui.emit(keys[1], 1)  # Pressiona segunda tecla ex: F5
        ui.emit(keys[1], 0)  # Solta segunda tecla
        ui.emit(keys[0], 0)  # Solta primeira tecla
