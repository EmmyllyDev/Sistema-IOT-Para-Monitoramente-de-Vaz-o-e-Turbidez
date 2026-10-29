"""Finge ser o ESP32 e envia leituras para o SIGUÁ.

Faz exatamente a mesma requisição HTTP que o firmware faz — mesma URL,
mesmo cabeçalho, mesmo JSON. Serve para testar o caminho do sensor antes
de ter o hardware na mão, e para isolar o problema depois: se o simulador
grava e o ESP32 não, o problema está no ESP32 ou na rede dele, não no site.

Uso:
    python firmware/simular_sensor.py --token SEU_TOKEN
    python firmware/simular_sensor.py --token SEU_TOKEN --quantas 12 --intervalo 0
    python firmware/simular_sensor.py --token SEU_TOKEN --nivel 45 --turbidez 2.8

    # apaga as leituras de sensor que este script criou
    python firmware/simular_sensor.py --limpar
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request

PADRAO_URL = "http://127.0.0.1:8000/monitoramento/api/sensor/"


def enviar(url, token, nivel, turbidez):
    """Uma leitura. Devolve (codigo, corpo) como o ESP32 veria."""
    dados = {}
    if nivel is not None:
        dados["nivel_cm"] = round(nivel, 2)
    if turbidez is not None:
        dados["turbidez_ntu"] = round(turbidez, 2)

    req = urllib.request.Request(
        url,
        data=json.dumps(dados).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        bruto = e.read().decode()
        try:
            return e.code, json.loads(bruto)
        except ValueError:
            return e.code, bruto[:300]
    except urllib.error.URLError as e:
        return None, f"nao alcancei {url}: {e.reason}"


def limpar():
    """Apaga do banco toda leitura com origem 'sensor'.

    Use antes de colocar o sistema em uso real, para o histórico oficial
    não começar com dados de teste.
    """
    import os
    import sys

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, raiz)
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(raiz, ".env"))
    except ImportError:
        pass
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")

    import django

    django.setup()
    from monitoramento.models import LeituraSensor

    qs = LeituraSensor.objects.filter(origem=LeituraSensor.ORIGEM_SENSOR)
    quantas = qs.count()
    if not quantas:
        print("Nenhuma leitura de sensor no banco.")
        return
    resposta = input(f"Apagar {quantas} leitura(s) de sensor? (digite sim) ").strip()
    if resposta.lower() != "sim":
        print("Nada apagado.")
        return
    qs.delete()
    print(f"{quantas} leitura(s) de sensor apagada(s).")


def main():
    p = argparse.ArgumentParser(description="Simula o ESP32 do SIGUÁ.")
    p.add_argument("--token", help="Token do sensor (Configurações › Token do sensor)")
    p.add_argument("--url", default=PADRAO_URL, help=f"Padrão: {PADRAO_URL}")
    p.add_argument("--quantas", type=int, default=1, help="Quantas leituras enviar")
    p.add_argument("--intervalo", type=float, default=2.0,
                   help="Segundos entre envios (0 manda em sequência)")
    p.add_argument("--nivel", type=float,
                   help="Altura fixa em cm. Sem isso, sorteia entre 25 e 70")
    p.add_argument("--turbidez", type=float,
                   help="Turbidez fixa em NTU. Sem isso, sorteia entre 0,3 e 4,5")
    p.add_argument("--limpar", action="store_true",
                   help="Apaga as leituras de sensor do banco e sai")
    a = p.parse_args()

    if a.limpar:
        limpar()
        return

    if not a.token:
        p.error("informe --token (ou use --limpar)")

    gravadas = 0
    for i in range(a.quantas):
        nivel = a.nivel if a.nivel is not None else round(random.uniform(25, 70), 1)
        turbidez = (a.turbidez if a.turbidez is not None
                    else round(random.uniform(0.3, 4.5), 2))

        codigo, corpo = enviar(a.url, a.token, nivel, turbidez)
        marca = "ok " if codigo == 201 else "ERRO"
        print(f"[{i + 1}/{a.quantas}] {marca} HTTP {codigo} "
              f"| {nivel} cm, {turbidez} NTU -> {corpo}")

        if codigo == 201:
            gravadas += 1
        elif codigo == 401:
            print("Token recusado. Pegue o token atual em Configurações.")
            break
        elif codigo is None:
            print("O servidor nao respondeu. Ele esta rodando? A URL esta certa?")
            break

        if a.intervalo and i + 1 < a.quantas:
            time.sleep(a.intervalo)

    print(f"\n{gravadas} de {a.quantas} leitura(s) gravada(s).")


if __name__ == "__main__":
    main()
