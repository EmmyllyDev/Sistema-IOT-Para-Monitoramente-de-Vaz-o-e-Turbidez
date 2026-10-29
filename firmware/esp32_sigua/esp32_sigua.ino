// ═══════════════════════════════════════════════════════════
//  SIGUA — Sistema Completo v7
//  Turbidez + Vazão + Ciclo automático de 30 minutos
// ═══════════════════════════════════════════════════════════
#include <WiFi.h>
#include <HTTPClient.h>
#include "credenciais.h"
#define VALVULA_SUPERIOR 25
#define VALVULA_INFERIOR 26
#define BOIA_SUPERIOR    32
#define BOIA_INFERIOR    33
#define PINO_TURBIDEZ    34
#define PINO_TRIG        18
#define PINO_ECHO        19

// ── MODO DE TESTE ──
// Deixe em true para validar o envio: o ciclo inteiro passa a durar menos de
// 1 minuto em vez de ~37. Volte para false antes de instalar na ETA.
#define MODO_TESTE true

// ── SÓ A CALHA ──
// Em true, ignora válvulas, boias e turbidez: só lê o ultrassônico e manda
// a lâmina. As válvulas ficam fechadas. Serve para testar a calha sozinha,
// sem precisar do reservatório montado. Volte para false para o ciclo real.
#define SOMENTE_CALHA true

// De quanto em quanto tempo manda a lâmina no modo só-calha.
const long INTERVALO_CALHA_MS = MODO_TESTE ? 30000L : 1800000L;

// Distância do sensor até o FUNDO da calha, medida com a calha SECA.
// Atenção: não é a mesma coisa que ALTURA_CALHA_CM. 92 cm é o quanto a
// calha comporta de água; esta aqui é onde o sensor está montado. As duas
// só coincidem se ele estiver exatamente na borda superior. Errar este
// número desloca toda a vazão — meça com trena antes de confiar no valor.
const float DISTANCIA_SENSOR_FUNDO_CM = 92.0;   // <<< MEÇA E AJUSTE

const float ALTURA_CALHA_CM       = 92.0; // altura máxima
const int   AMOSTRAS_TURBIDEZ     = MODO_TESTE ? 5 : 200;
const long  TEMPO_REPOUSO_MS      = MODO_TESTE ? 10000L  : 300000L;   // 5min para repouso d água
const long  TEMPO_ENTRE_CICLOS_MS = MODO_TESTE ? 30000L  : 1800000L;  // 30 minutos para o proximo ciclo (60*30*1000)
const long  TEMPO_ESVAZIAMENTO_MS = 5000;    // 5 segundos

const int N_TAB = 27;
const float lamina_tab[N_TAB] = {
  10.0, 15.0, 20.0, 22.5, 25.0, 27.5, 30.0, 32.5, 35.0,
  37.5, 40.0, 42.5, 45.0, 47.5, 50.0, 52.5, 55.0, 57.5,
  60.0, 62.5, 65.0, 67.5, 70.0, 72.5, 75.0, 77.5, 80.0
};
const float vazao_tab[N_TAB] = {
  10,  30,  50,  60,  70,  80,  90, 105, 115,
  130, 140, 155, 170, 185, 200, 215, 230, 250,
  265, 280, 295, 315, 330, 350, 370, 390, 410
};

enum Estado { ENCHENDO, REPOUSO, LEITURA, ESVAZIANDO, AGUARDANDO };
Estado estado = ENCHENDO;

unsigned long inicio_repouso        = 0;
unsigned long inicio_esvaziamento   = 0;
unsigned long inicio_aguardo        = 0;
unsigned long ultimo_log_repouso    = 0;
unsigned long ultimo_log_aguardo    = 0;
unsigned long ultimo_sonic          = 0;
unsigned long ultimo_debug          = 0;
bool aguardando_esvaziamento        = false;

// Última lâmina boa lida pelo ultrassônico, e quando foi lida. A leitura
// acontece a cada 2 s no loop, mas o envio só no fim do ciclo — guardar o
// instante evita mandar um valor de minutos atrás como se fosse de agora.
float         ultima_lamina    = -1;
unsigned long ultima_lamina_ms = 0;

// Acima disso a lâmina é considerada velha demais para ir junto.
const unsigned long VALIDADE_LAMINA_MS = 60000;

float calcularVazao(float lamina) {
  if (lamina <= lamina_tab[0])       return vazao_tab[0];
  if (lamina >= lamina_tab[N_TAB-1]) return vazao_tab[N_TAB-1];
  for (int i = 0; i < N_TAB - 1; i++) {
    if (lamina >= lamina_tab[i] && lamina < lamina_tab[i+1]) {
      float t = (lamina - lamina_tab[i]) / (lamina_tab[i+1] - lamina_tab[i]);
      return vazao_tab[i] + t * (vazao_tab[i+1] - vazao_tab[i]);
    }
  }
  return -1;
}

float lerTurbidez() {
  long soma = 0;
  for (int i = 0; i < 20; i++) {
    soma += analogRead(PINO_TURBIDEZ);
    delay(10);
  }
  float tensao = (soma / 20.0 / 4095.0) * 5.0;
  float ntu = (1.0 - (tensao / 5.0)) * 3000.0;
  return constrain(ntu, 0, 3000);
}

void lerVazao() {
  float leituras[10];
  int n = 0;

  for (int i = 0; i < 10; i++) {
    digitalWrite(PINO_TRIG, LOW);
    delayMicroseconds(5);
    digitalWrite(PINO_TRIG, HIGH);
    delayMicroseconds(20);
    digitalWrite(PINO_TRIG, LOW);

    unsigned long dur = pulseIn(PINO_ECHO, HIGH, 60000);
    if (dur > 0 && dur < 35000) {
      leituras[n++] = dur / 58.0;
    }
    delay(60);
  }

  if (n == 0) {
    Serial.println("[VAZÃO] Sem leitura");
    return;
  }

  // Ordena as leituras (bubble sort)
  for (int i = 0; i < n - 1; i++) {
    for (int j = 0; j < n - i - 1; j++) {
      if (leituras[j] > leituras[j + 1]) {
        float tmp = leituras[j];
        leituras[j] = leituras[j + 1];
        leituras[j + 1] = tmp;
      }
    }
  }

  // Pega a mediana (valor do meio)
  float dist = leituras[n / 2];
  // A altura da água é o quanto falta da distância medida até o fundo.
  float lamina = DISTANCIA_SENSOR_FUNDO_CM - dist;
  float vazao  = calcularVazao(lamina);

  Serial.print("[VAZÃO] Dist: ");       Serial.print(dist, 1);
  Serial.print(" cm | Lâmina: ");       Serial.print(lamina, 1);
  Serial.print(" cm | Vazão: ");        Serial.print(vazao, 1);
  Serial.print(" l/s | Amostras: ");    Serial.print(n);
  Serial.println("/10");

  // Guarda para o envio. A vazão acima é só para o Serial: quem converte
  // cm em L/s no registro oficial é o servidor, pela tabela dele.
  ultima_lamina    = lamina;
  ultima_lamina_ms = millis();
}

// ═══════════════════════════════════════════════════════════
//  Envio para o SIGUA
// ═══════════════════════════════════════════════════════════

bool conectarWifi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.print("[WIFI] Conectando em ");
  Serial.print(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);

  unsigned long limite = millis() + 20000UL;
  while (WiFi.status() != WL_CONNECTED && millis() < limite) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Falhou. Confira SSID e senha em credenciais.h");
    return false;
  }
  Serial.print("[WIFI] Conectado. IP do ESP32: ");
  Serial.println(WiFi.localIP());
  return true;
}

// Manda a leitura. Passe -1 no que não tiver: o campo sai do JSON e o
// servidor grava o resto. Nenhum parâmetro é obrigatório.
bool enviarSIGUA(float turbidez, float lamina) {
  if (!conectarWifi()) return false;

  String corpo = "{";
  bool vazio = true;
  if (turbidez >= 0) {
    corpo += "\"turbidez_ntu\":" + String(turbidez, 2);
    vazio = false;
  }
  if (lamina >= 0) {
    if (!vazio) corpo += ",";
    corpo += "\"nivel_cm\":" + String(lamina, 2);
    vazio = false;
  }
  corpo += "}";

  if (vazio) {
    Serial.println("[SIGUA] Nada medido neste ciclo; nao enviei.");
    return false;
  }

  for (int t = 1; t <= 3; t++) {
    HTTPClient http;
    http.begin(SIGUA_URL);
    http.addHeader("Content-Type", "application/json");
    // Sem este cabeçalho o servidor responde 401 e descarta a leitura.
    http.addHeader("Authorization", String("Bearer ") + SIGUA_TOKEN);
    http.setTimeout(15000);

    Serial.print("[SIGUA] Enviando: ");
    Serial.println(corpo);

    int codigo = http.POST(corpo);
    String resposta = http.getString();
    http.end();

    Serial.print("[SIGUA] HTTP ");
    Serial.print(codigo);
    Serial.print(" -> ");
    Serial.println(resposta);

    if (codigo == 201) {
      Serial.println("[SIGUA] ✓ Leitura gravada no sistema.");
      return true;
    }
    // Repetir com o mesmo token ou o mesmo dado inválido não muda nada.
    if (codigo == 401) {
      Serial.println("[SIGUA] Token recusado. Veja SIGUA_TOKEN em credenciais.h.");
      return false;
    }
    if (codigo == 400) {
      Serial.println("[SIGUA] Servidor recusou os dados (resposta acima).");
      return false;
    }

    Serial.print("[SIGUA] Falhou. Tentativa ");
    Serial.print(t); Serial.println(" de 3.");
    delay(5000);
  }
  return false;
}

void setup() {
  Serial.begin(115200);

  pinMode(VALVULA_SUPERIOR, OUTPUT);
  pinMode(VALVULA_INFERIOR, OUTPUT);
  digitalWrite(VALVULA_SUPERIOR, LOW);
  digitalWrite(VALVULA_INFERIOR, LOW);

  pinMode(BOIA_SUPERIOR, INPUT_PULLUP);
  pinMode(BOIA_INFERIOR, INPUT_PULLUP);
  pinMode(PINO_TRIG, OUTPUT);
  pinMode(PINO_ECHO, INPUT);
  digitalWrite(PINO_TRIG, LOW);

  Serial.println("\n=== SIGUA — Sistema Iniciado ===");
  if (MODO_TESTE) {
    Serial.println("*** MODO_TESTE ligado: ciclo curto. Desligue antes de instalar. ***");
  }

  conectarWifi();

  if (SOMENTE_CALHA) {
    // Nada de válvulas nem boias: elas ficam como foram inicializadas,
    // fechadas. O loop cuida só do ultrassônico.
    Serial.println("*** SOMENTE_CALHA: valvulas fechadas, turbidez desligada. ***");
    Serial.print("*** Distancia sensor->fundo configurada: ");
    Serial.print(DISTANCIA_SENSOR_FUNDO_CM, 1);
    Serial.println(" cm ***");
    Serial.print("*** Enviando a cada ");
    Serial.print(INTERVALO_CALHA_MS / 1000);
    Serial.println(" s ***");
    return;
  }

  int boia_sup = digitalRead(BOIA_SUPERIOR);
  int boia_inf = digitalRead(BOIA_INFERIOR);

  Serial.print("Boia SUP (32): "); Serial.print(boia_sup);
  Serial.println(boia_sup == HIGH ? " → vazio" : " → cheio");
  Serial.print("Boia INF (33): "); Serial.print(boia_inf);
  Serial.println(boia_inf == LOW ? " → vazio" : " → cheio");

  // SUP HIGH = vazio → encher
  // SUP LOW  = cheio → repouso
  if (boia_sup == HIGH) {
    Serial.println("[ENCHENDO] Vazio! Abrindo válvula superior...");
    digitalWrite(VALVULA_SUPERIOR, HIGH);
    estado = ENCHENDO;
  } else {
    Serial.println("[REPOUSO] Cheio! Aguardando repouso...");
    inicio_repouso     = millis();
    ultimo_log_repouso = millis();
    estado = REPOUSO;
  }
}

void loop() {

  if (millis() - ultimo_sonic >= 2000) {
    lerVazao();
    ultimo_sonic = millis();
  }

  // ── Modo só-calha: lê o ultrassônico e manda a lâmina, sem o ciclo. ──
  if (SOMENTE_CALHA) {
    static unsigned long proximo_envio_calha = 0;

    // Subtração em vez de "millis() >= alvo": continua certo quando o
    // contador dá a volta, a cada ~49 dias.
    if ((long)(millis() - proximo_envio_calha) >= 0) {
      bool recente = (ultima_lamina >= 0) &&
                     (millis() - ultima_lamina_ms < VALIDADE_LAMINA_MS);
      if (recente) {
        // -1 na turbidez: o campo sai do JSON e só a lâmina é gravada.
        enviarSIGUA(-1, ultima_lamina);
      } else {
        Serial.println("[SIGUA] Sem lamina valida ainda; nao enviei.");
      }
      proximo_envio_calha = millis() + INTERVALO_CALHA_MS;
    }
    return;
  }

  switch (estado) {

    // SUP LOW = cheio → fecha válvula
    case ENCHENDO:
      if (digitalRead(BOIA_SUPERIOR) == LOW) {
        digitalWrite(VALVULA_SUPERIOR, LOW);
        inicio_repouso     = millis();
        ultimo_log_repouso = millis();
        estado = REPOUSO;
        Serial.println("[REPOUSO] Nível máximo! Aguardando...");
      }
      break;

    // Água parada pra acomodar partículas
    case REPOUSO:
      if (millis() - ultimo_log_repouso >= 1000) {
        Serial.print("[REPOUSO] ");
        Serial.print((millis() - inicio_repouso) / 1000);
        Serial.println("s");
        ultimo_log_repouso = millis();
      }
      if (millis() - inicio_repouso >= TEMPO_REPOUSO_MS) {
        estado = LEITURA;
        Serial.println("[LEITURA] Iniciando 50 amostras...");
      }
      break;

    // 50 amostras → média → resultado
    case LEITURA: {
      float soma = 0;
      for (int i = 0; i < AMOSTRAS_TURBIDEZ; i++) {
        soma += lerTurbidez();
        Serial.print(".");
        delay(200);
      }
      float media = soma / AMOSTRAS_TURBIDEZ;
      Serial.println();
      Serial.print("[RESULTADO] Turbidez média: ");
      Serial.print(media, 2);
      Serial.print(" NTU — ");
      if (media <= 5.0)
        Serial.println("✓ DENTRO DO LIMITE (Portaria 888/2021)");
      else
        Serial.println("✗ ACIMA DO LIMITE — ALERTA!");

      // Envia junto a lâmina, se ela for recente. Uma lâmina de minutos
      // atrás seria registrada com a hora de agora e mentiria a vazão.
      {
        bool recente = (ultima_lamina >= 0) &&
                       (millis() - ultima_lamina_ms < VALIDADE_LAMINA_MS);
        if (!recente && ultima_lamina >= 0) {
          Serial.println("[SIGUA] Lamina velha demais; envio so a turbidez.");
        }
        enviarSIGUA(media, recente ? ultima_lamina : -1);
      }

      digitalWrite(VALVULA_INFERIOR, HIGH);
      aguardando_esvaziamento = false;
      estado = ESVAZIANDO;
      Serial.println("[ESVAZIANDO] Válvula inferior aberta...");
      break;
    }

    // INF LOW = vazio → conta 5s e fecha
    case ESVAZIANDO:
      if (millis() - ultimo_debug >= 1000) {
        Serial.print("[ESVAZIANDO] Boia INF: ");
        Serial.println(digitalRead(BOIA_INFERIOR) == LOW ? "vazio" : "tem água");
        ultimo_debug = millis();
      }
      if (!aguardando_esvaziamento) {
        if (digitalRead(BOIA_INFERIOR) == LOW) {
          inicio_esvaziamento     = millis();
          aguardando_esvaziamento = true;
          Serial.println("[ESVAZIANDO] Nível baixo — aguardando 5s...");
        }
      } else {
        if (millis() - inicio_esvaziamento >= TEMPO_ESVAZIAMENTO_MS) {
          digitalWrite(VALVULA_INFERIOR, LOW);
          aguardando_esvaziamento = false;
          inicio_aguardo          = millis();
          ultimo_log_aguardo      = millis();
          estado = AGUARDANDO;
          Serial.println("[AGUARDANDO] Ciclo completo! Próximo em 30 min.\n");
        }
      }
      break;

    // Espera 30 minutos e reinicia
    case AGUARDANDO:
      if (millis() - ultimo_log_aguardo >= 300000) {
        int min_rest = 30 - ((millis() - inicio_aguardo) / 60000);
        Serial.print("[AGUARDANDO] Próximo ciclo em ");
        Serial.print(min_rest);
        Serial.println(" min.");
        ultimo_log_aguardo = millis();
      }
      if (millis() - inicio_aguardo >= TEMPO_ENTRE_CICLOS_MS) {
        estado = ENCHENDO;
        digitalWrite(VALVULA_SUPERIOR, HIGH);
        Serial.println("[ENCHENDO] Novo ciclo iniciado!\n");
      }
      break;
  }
}