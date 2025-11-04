"""
Simulador físico realista de um motor industrial com falhas e reparos.

Modos de operação:
------------------
1. base  - Gera uma base histórica finita (para treinamento e testes)
2. ao_vivo - Executa continuamente, salvando em tempo real (para EdgePHM)

Objetivo:
---------
- Simular comportamento físico realista com degradação, falhas e reparos.
- Incluir variedade de falhas: sobreaquecimento, sobrecorrente, vibração e perda de torque.
- Gerar campo 'drift_score' para representar o grau de anomalia.
- Permitir operação contínua para alimentar o nó de borda (EdgePHM).

Cada ciclo percorre as fases:
    normal  - falha - reparo - (volta a normal)
"""

import pandas as pd
import numpy as np
import time
from datetime import datetime

# CONFIGURAÇÕES PRINCIPAIS

MODO = "base"   # Opções: "base" (gera CSV histórico) | "ao_vivo" (loop infinito)
ARQ_SAIDA = "base_treinamento.csv" if MODO == "base" else "leituras_ativas.csv"

DURACAO = 1200 if MODO == "base" else None   # Ciclos para base, infinito se ao vivo
TICK_INTERVAL = 1.0                          # Intervalo entre leituras (s)
np.random.seed(42)

# Limites físicos de segurança
LIM_TEMPERATURA = 70.0
LIM_CORRENTE = 6.5
LIM_VIBRACAO = 1.2
LIM_RPM = 1000

# Valores nominais
corrente = 5.0
temperatura = 35.0
vibracao = 0.5
rpm = 1500

# Estado inicial
fase = "normal"
tipo_falha = None
tempo_reparo = None
drift_score = 0.0

leituras = []
tick = 0

print(f"Simulador iniciado no modo: {MODO.upper()}")


# LOOP PRINCIPAL

while True:
    # 1. FASE NORMAL --------------------------------------
    if fase == "normal":
        corrente += np.random.normal(0.002, 0.02)
        temperatura += np.random.normal(0.01, 0.05)
        vibracao += np.random.normal(0.001, 0.005)
        rpm += np.random.normal(0, 3)

        # Anomalia crescente (drift leve)
        drift_score = max(0, min(1, (temperatura - 35) / 35))

        # Probabilidade de falha aumenta com desgaste
        prob_falha = min(0.0008 * (1 + drift_score**2), 0.08)

        if np.random.rand() < prob_falha:
            # Escolhe aleatoriamente o tipo de falha (maior variedade)
            tipo_falha = np.random.choice([
                "sobreaquecimento", "sobrecorrente",
                "excesso_vibracao", "perda_torque"
            ], p=[0.25, 0.25, 0.25, 0.25])

            fase = "falha"
            tempo_reparo = tick + np.random.randint(80, 150)

    # 2. FASE DE FALHA ------------------------------------
    elif fase == "falha":
        if tipo_falha == "sobreaquecimento":
            temperatura += np.random.normal(0.25, 0.2)
            corrente += np.random.normal(0.05, 0.08)
            rpm -= np.random.normal(3, 2)

        elif tipo_falha == "sobrecorrente":
            corrente += np.random.normal(0.35, 0.15)
            temperatura += np.random.normal(0.05, 0.08)
            rpm -= np.random.normal(4, 3)

        elif tipo_falha == "excesso_vibracao":
            vibracao += np.random.normal(0.06, 0.02)
            corrente += np.random.normal(0.02, 0.02)
            rpm -= np.random.normal(8, 4)

        elif tipo_falha == "perda_torque":
            rpm -= np.random.normal(10, 4)
            corrente += np.random.normal(0.05, 0.05)
            vibracao += np.random.normal(0.01, 0.01)

        # Saturação física
        temperatura = min(temperatura, 100)
        corrente = min(corrente, 8)
        vibracao = min(vibracao, 2)
        rpm = max(rpm, 400)

        drift_score = 1.0

        # Fim da falha → entra em reparo
        if tempo_reparo is not None and tick >= tempo_reparo:
            fase = "reparo"

    # 3. FASE DE REPARO -----------------------------------
    elif fase == "reparo":
        corrente += (5.0 - corrente) * 0.15 + np.random.normal(0, 0.02)
        temperatura += (35.0 - temperatura) * 0.15 + np.random.normal(0, 0.1)
        vibracao += (0.5 - vibracao) * 0.15 + np.random.normal(0, 0.01)
        rpm += (1500 - rpm) * 0.15 + np.random.normal(0, 5)

        drift_score = max(0.0, drift_score - 0.05)

        if (abs(corrente - 5.0) < 0.1 and
            abs(temperatura - 35.0) < 1.0 and
            abs(vibracao - 0.5) < 0.05):
            fase = "normal"
            tipo_falha = None
            drift_score = 0.0

    # 4. REGISTRO DE LEITURA ------------------------------
    leituras.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "tick": tick,
        "corrente": round(corrente, 3),
        "temperatura": round(temperatura, 3),
        "vibracao": round(vibracao, 3),
        "rpm": round(rpm, 2),
        "fase": fase,
        "tipo_falha": tipo_falha or "nenhuma",
        "drift_score": round(drift_score, 3)
    })

    # Gravação incremental
    pd.DataFrame(leituras[-1:]).to_csv(
        ARQ_SAIDA,
        mode="a",
        index=False,
        header=not (tick > 0 or MODO == "ao_vivo")
    )

    # Tempo entre leituras
    time.sleep(TICK_INTERVAL)
    tick += 1

    # Encerramento no modo histórico
    if MODO == "base" and tick >= DURACAO:
        print(f"Base histórica gerada com sucesso em: {ARQ_SAIDA}")
        break
