# Sensores do SIGUÁ — ESP32

Como ligar o ESP32 no sistema e como testar se o dado está realmente chegando.

## O que o sensor manda

Dois valores, a cada 30 minutos:

| Campo | O que é | Unidade |
|---|---|---|
| `nivel_cm` | altura da lâmina na calha Parshall | cm |
| `turbidez_ntu` | turbidez da água tratada | NTU |

O ESP32 **não** manda a vazão. Ele manda a altura em cm e o servidor converte
pela tabela da ETA (`monitoramento/vazao.py`). Se a tabela for corrigida, o
ESP32 não precisa ser reprogramado.

Ele também **não** manda o horário nem diz se a água está conforme — as duas
coisas são decididas pelo servidor. O ESP32 não tem relógio de bateria, e
deixar o aparelho declarar conformidade seria confiar numa informação que
qualquer um na rede poderia falsificar.

## Endereço e autenticação

```
POST http://<ip-ou-dominio>/monitoramento/api/sensor/
Content-Type: application/json
Authorization: Bearer <token-do-sensor>

{"nivel_cm": 45.0, "turbidez_ntu": 2.8}
```

O token fica em **Configurações › Token do sensor**, dentro do site. Sem o
cabeçalho `Authorization`, a resposta é **401** e a leitura é descartada.

Respostas possíveis:

| Código | Significa |
|---|---|
| 201 | gravado — o corpo traz `id`, `horario`, `vazao_ls` e `status_conformidade` |
| 400 | dado inválido (texto onde era número, por exemplo) |
| 401 | token ausente, errado ou regerado no site |

## Preparar o firmware

1. Copie `esp32_sigua/credenciais_exemplo.h` como `esp32_sigua/credenciais.h`.
2. Preencha rede, URL e token. (`credenciais.h` está no `.gitignore`.)
3. Em `esp32_sigua.ino`, meça e ajuste **`DISTANCIA_SENSOR_FUNDO_CM`**: é a
   distância do sensor até o fundo da calha, com a calha seca. Errar isso
   desloca toda a vazão.
4. Ajuste a curva em `lerTurbidezNtu()` com a calibração do seu módulo. A que
   está no arquivo é genérica e serve só para o sketch compilar e rodar.
5. Na Arduino IDE: placa *ESP32 Dev Module*, e as bibliotecas `WiFi` e
   `HTTPClient` já vêm com o core do ESP32.

**Para testar, baixe o intervalo.** Esperar 30 minutos por envio torna o teste
inviável. Troque temporariamente:

```cpp
const unsigned long INTERVALO_MS = 30UL * 1000UL;   // 30 s só para teste
```

e devolva para `30UL * 60UL * 1000UL` antes de instalar em campo.

## Testar sem o hardware

`simular_sensor.py` faz a **mesma requisição** que o firmware faz. Serve para
provar que o site grava antes de você mexer no ESP32 — e depois, para isolar
o problema: se o simulador grava e o ESP32 não, o defeito está no ESP32 ou na
rede dele, não no site.

```bash
# uma leitura
python firmware/simular_sensor.py --token SEU_TOKEN

# doze leituras em sequência, como um dia de operação
python firmware/simular_sensor.py --token SEU_TOKEN --quantas 12 --intervalo 0

# valor exato, para conferir a conversão (45 cm tem que dar 170 L/s)
python firmware/simular_sensor.py --token SEU_TOKEN --nivel 45 --turbidez 2.8

# do ESP32 para um servidor na rede, informe a URL
python firmware/simular_sensor.py --token SEU_TOKEN \
    --url http://192.168.1.122:8000/monitoramento/api/sensor/
```

Antes de colocar o sistema em uso real, limpe os dados de teste para o
histórico oficial não começar sujo:

```bash
python firmware/simular_sensor.py --limpar
```

Apaga só as leituras com origem `sensor`; as do operador ficam.

## Rede

O ESP32 e o servidor **não precisam** estar na mesma rede — o ESP32 só precisa
alcançar o endereço. Na prática:

- **Servidor na máquina local (fase de teste):** os dois na mesma rede Wi-Fi.
  Use o IP da máquina, não `127.0.0.1` — para o ESP32, `127.0.0.1` é ele mesmo.
- **Servidor na nuvem:** qualquer rede com internet serve. Use a URL `https`.

O IP da máquina vem do DHCP e muda. Se o ESP32 apontar para um IP que mudou,
ele para de enviar sem erro aparente. Reserve um IP fixo para a máquina no
roteador antes de instalar em campo.

## Quando não chega nada

Confira na ordem:

1. **Monitor serial** (115200 baud). Ele imprime o JSON enviado e o código HTTP.
2. **HTTP 401** → token errado ou regerado no site. Pegue o atual em Configurações.
3. **Sem resposta / timeout** → IP errado, servidor desligado, ou firewall do
   Windows bloqueando a porta.
4. **Nível "sem eco"** → o ultrassônico não recebeu retorno em 7 disparos.
   Verifique a fiação e se ele está apontado para a água, perpendicular à
   superfície.
5. **Chegou, mas a vazão parece errada** → confira `DISTANCIA_SENSOR_FUNDO_CM`.
   A tabela está em `monitoramento/vazao.py`: 45 cm tem que dar 170 L/s.

## Onde o dado aparece

- **Dashboard** — o card de vazão mostra os cm lidos e a vazão convertida. O
  anel de amostras conta **só o operador**, de propósito: a meta de 360 é a
  amostragem dele, e o sensor, a cada 30 min, entraria quatro vezes acima.
- **Relatório** — cada parâmetro mostra quantas amostras vieram do sensor e
  quantas do operador.
