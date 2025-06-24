#!/usr/bin/env python3
import time
import sys
import select

btns = ["G1", "G2", "A", "B", "C", "D", "SU", "SD", "SL", "SR"]
resultados = {}

TIMEOUT = 4  # segundos para esperar o botão
MODE = "D"


def wait_for_data(f, timeout=TIMEOUT, btn=None):
    rlist, _, _ = select.select([f], [], [], timeout)
    if rlist:
        if MODE == "D":
            if btn and btn in ["G1", "G2"]:
                return f.read(10)
        return f.read(6)
    else:
        return None


print(">>> Pressione e solte cada botão quando solicitado <<<")
print(f">>> Aguarde até {TIMEOUT}s para cada botão, senão pula automático <<<\n")

with open("/dev/hidraw4", "rb") as f:
    for btn in btns:
        if MODE == "D" and btn in ["SU", "SD", "SL", "SR"]:
            continue
        print(f"\nAgora pressione e solte o botão: {btn}")
        data = wait_for_data(f, btn=btn)
        if not data:
            print(f">>> Tempo esgotado, pulando {btn}")
            continue
        meio = len(data) // 2
        parte1 = list(data[:meio])
        parte2 = list(data[meio:])
        resultados[btn] = (parte1, parte2)
        print(f"Capturado: {parte1} (pressionar) e {parte2} (soltar)")

print("\n--- Resultados ---\n")
for btn, (p1, p2) in resultados.items():
    print(f"{btn} = [{', '.join(map(str, p1))}] [{', '.join(map(str, p2))}]")
