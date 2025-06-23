import os
import glob
import time
import subprocess
import threading

VENDOR_ID = "248a"
PRODUC_ID = "8266"


def is_interest_device(hidraw_path):
    try:
        output = subprocess.check_output(
            ["udevadm", "info", "-a", "-n", hidraw_path], text=True
        )
        return VENDOR_ID in output.lower() and PRODUC_ID in output.lower()
    except subprocess.CalledProcessError:
        return False


def find_hidraws():
    devicelist = []
    for path in glob.glob("/dev/hidraw*"):
        if is_interest_device(path):
            devicelist.append(path)
    return devicelist


def inditify_event(data):
    event_type = data[3]
    button_code = data[5]

    if event_type == 100:
        if button_code == 113:
            return "Button 02 - Pressed"
        # etc, preencha com mais códigos conhecidos
    return "Evento desconhecido"


def process_data_bytes(data):

    b = list(data)

    print("RAW: ", b)

    # byte5 = b[5]
    #
    # # Botão 02 (Laser)
    # if byte5 == 100:
    #     print("Botão 02 (laser) pressionado")
    #
    #     # Botão 07
    # elif byte5 == 122:
    #     print("Botão 07 pressionado A")
    # elif byte5 == 123:
    #     print("Botão 07 pressionado B")
    # elif byte5 == 124:
    #     print("Botão 07 Segurando")
    # elif byte5 == 125:
    #     print("Botão 07 Solto")
    #
    # # Botão 06
    # elif byte5 == 116:
    #     print("Botão 06 pressionado A")
    # elif byte5 == 117:
    #     print("Botão 06 pressionado B")
    # elif byte5 == 118:
    #     print("Botão 06 Segurando")
    # elif byte5 == 119:
    #     print("Botão 06 Solto")
    #
    # # else:
    # print(f"[{path}] Raw: {list(data_bytes)}")
    #


def read_full_packets(f):
    buffer = bytearray()
    while True:
        b = f.read(1)
        if not b:
            break  # fim do arquivo ou erro
        buffer += b
        if b[0] == 182:  # byte final do pacote
            yield bytes(buffer)
            buffer.clear()


def monitor_device(path):
    print(f"🟢 Monitorando {path}...")
    try:
        with open(path, "rb") as f:
            for packet in read_full_packets(f):
                process_data_bytes(packet)
            # while True:
            #     data = f.read(32)
            #     if data:
            #         processa_pacote(data)
    except PermissionError:
        print(
            f"🚫 Sem permissão para acessar {path} (tente ajustar udev ou rodar com sudo)"
        )
    except KeyboardInterrupt:
        print(f"\nFinalizando {path}")
    except Exception as e:
        print(f"⚠️ Erro em {path}: {e}")


if __name__ == "__main__":
    paths = find_hidraws()
    if not paths:
        print("⚠️ Nenhum dispositivo encontrado via udevadm.")
        exit(1)

    print("Dispositivos encontrados:")
    for p in paths:
        print(" -", p)

    print("\nIniciando monitoramento...\n(Pressione Ctrl+C para sair)\n")
    threads = []

    for path in paths:
        t = threading.Thread(target=monitor_device, args=(path,), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando todos os monitores.")
