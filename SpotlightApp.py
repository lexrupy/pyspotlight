import tkinter as tk
from tkinter import scrolledtext
import subprocess
import threading
import sys
import os
import signal
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from screeninfo import get_monitors


class PySpotlightApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Py-Spotlight")
        self.icon = None

        # Criar interface
        self.title_label = tk.Label(
            root, text="Py-Spotlight", font=("Arial", 16, "bold")
        )
        self.title_label.pack(pady=10)

        self.monitor_frame = tk.Frame(root)
        self.monitor_frame.pack(padx=10, pady=5, anchor="w")

        tk.Label(self.monitor_frame, text="Selecionar monitor:").pack(side=tk.LEFT)

        self.monitor_var = tk.StringVar()
        self.monitor_combo = tk.OptionMenu(self.monitor_frame, self.monitor_var, [])
        self.monitor_combo.config(anchor="w", justify="left")
        self.monitor_combo.pack(side=tk.LEFT, padx=5)

        self.refresh_monitors()

        self.start_button = tk.Button(
            self.monitor_frame,
            text="Reiniciar no monitor selecionado",
            command=self.restart_subprocess,
        )
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.log_text = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            height=20,
            bg="black",
            fg="lime",
            insertbackground="white",
        )
        self.log_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)

        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=10)

        self.clear_button = tk.Button(
            self.button_frame, text="Limpar Log", command=self.clear_log
        )
        self.clear_button.pack(side=tk.LEFT, padx=5)

        self.hide_button = tk.Button(
            self.button_frame, text="Ocultar", command=self.hide_to_tray
        )
        self.hide_button.pack(side=tk.LEFT, padx=5)

        self.exit_button = tk.Button(
            self.button_frame, text="Encerrar", command=self.exit_app
        )
        self.exit_button.pack(side=tk.LEFT, padx=5)

        self.process = None
        self.running = True
        self.start_subprocess()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def append_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def refresh_monitors(self):
        self.monitors = get_monitors()
        options = [
            f"{i}: {m.width}x{m.height} @ {m.x},{m.y}"
            + (" [Primário]" if m.is_primary else "")
            for i, m in enumerate(self.monitors)
        ]

        # Calcula o maior comprimento
        max_width = max(len(opt) for opt in options)

        # Atualiza o OptionMenu
        menu = self.monitor_combo["menu"]
        menu.delete(0, "end")
        for option in options:
            menu.add_command(
                label=option, command=lambda val=option: self.monitor_var.set(val)
            )

        self.monitor_var.set(options[0])

        # Atualiza o widget com largura ideal
        self.monitor_combo.config(width=max_width)

    def restart_subprocess(self):
        self.stop_subprocess()
        self.start_subprocess()

    def stop_subprocess(self):
        if self.process and self.process.poll() is None:
            try:
                if os.name == "nt":
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception as e:
                self.append_log(f"Erro ao parar subprocesso: {e}\n")
            self.process = None

    def start_subprocess(self):
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "monitor.py"
        )
        # Extrair índice do monitor selecionado
        selected = self.monitor_var.get()
        monitor_index = selected.split(":")[0] if ":" in selected else "0"

        self.process = subprocess.Popen(
            [sys.executable, "-u", script_path, "-s", monitor_index],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
        threading.Thread(target=self.read_output, daemon=True).start()

    def read_output(self):
        while self.running and self.process:
            if self.process.poll() is not None:
                break  # processo já terminou

            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                self.append_log(line)

    def hide_to_tray(self):
        self.root.withdraw()
        if self.icon is None:
            self.create_tray_icon()

    def create_tray_icon(self):
        def restore():
            self.root.after(0, self.root.deiconify)
            if self.icon:
                self.icon.stop()
                self.icon = None

        image = self.create_image()
        self.icon = pystray.Icon("Py-Spotlight", image, "Py-Spotlight")

        def run_icon():
            self.icon.run()

        threading.Thread(target=run_icon, daemon=True).start()

        # Aguarde um pouco e registre o clique
        def bind_click():
            import time

            time.sleep(0.3)
            try:
                self.icon._icon._on_click = lambda: restore()
            except Exception:
                pass

        threading.Thread(target=bind_click, daemon=True).start()

    def create_image(self):
        image = Image.new("RGB", (64, 64), "black")
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 48, 48), fill="lime")
        return image

    def exit_app(self):
        self.running = False
        if self.icon:
            self.icon.stop()
        if self.process and self.process.poll() is None:
            try:
                if os.name == "nt":
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PySpotlightApp(root)
    root.geometry("800x500")
    root.mainloop()
