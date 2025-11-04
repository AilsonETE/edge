import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
from river import drift, linear_model, optim, preprocessing


# CONFIGURAÇÕES

ARQ_SAIDA = "metricas_hi_ttf.csv"
ARQ_DRIFT = "metricas_drift.csv"
ARQ_FLAG_RECALIBRAR = "recalibrar.flag"
ARQ_FLAG_REPARO = "reparo.flag"
ARQ_SIMULADOR = "leituras_ativas.csv"

TICK_INTERVAL = 1.0
CALIBRACAO_INICIAL = 200
DELTA_ADWIN = 0.002

# OBJETOS DE APRENDIZADO

detector = drift.ADWIN(delta=DELTA_ADWIN)
scaler = preprocessing.StandardScaler()
modelo_TTF = linear_model.LinearRegression(optimizer=optim.SGD(0.01))

baseline = {"mu": None, "sigma": None}
estado = "Calibrando"
hi_hist = []
tick = 0


# Funções auxiliares

def ler_simulador():
    """Lê a última linha gerada pelo simulador"""
    try:
        df = pd.read_csv(ARQ_SIMULADOR)
        return df.iloc[-1]
    except Exception:
        return None

def salvar_metricas(linha):
    """Grava métricas contínuas"""
    new_file = not os.path.exists(ARQ_SAIDA)
    with open(ARQ_SAIDA, "a") as f:
        if new_file:
            f.write("timestamp,tick,HI,HI_suav,HI_deriv,TTF_estimado,risco_falha,estado\n")
        f.write(",".join(map(str, linha)) + "\n")

def salvar_drift_evento(hi):
    """Registra evento de drift"""
    df = pd.DataFrame([[datetime.now().isoformat(timespec="seconds"), hi]],
                      columns=["timestamp", "HI"])
    df.to_csv(ARQ_DRIFT, mode="a", index=False, header=not os.path.exists(ARQ_DRIFT))

def suavizar(valores, alpha=0.15):
    """Exponencial smoothing"""
    if not valores:
        return valores
    s = [valores[0]]
    for v in valores[1:]:
        s.append(alpha * v + (1 - alpha) * s[-1])
    return np.array(s)

def recalibrar_baseline():
    """Reseta baseline e detector"""
    global baseline, detector, estado
    baseline = {"mu": None, "sigma": None}
    detector = drift.ADWIN(delta=DELTA_ADWIN)
    estado = "Recalibrando"
    print("♻️ Recalibração de baseline iniciada...")



# Loop principal

print("Nó de borda EdgePHM v5 iniciado")
print("Iniciando calibração automática...")

while True:
    dado = ler_simulador()
    if dado is None:
        time.sleep(TICK_INTERVAL)
        continue

    tick += 1


    # Construção do Health Index (HI)
   
    corrente = float(dado["corrente"])
    temperatura = float(dado["temperatura"])
    vibracao = float(dado["vibracao"])

    # Combinação ponderada
    hi = 1 - (0.4 * corrente/10 + 0.3 * temperatura/100 + 0.3 * vibracao/10)
    hi = max(0, min(1, hi))  # limitar a 0–1
    hi_hist.append(hi)

  
    # Calibração inicial
    
    if baseline["mu"] is None and tick >= CALIBRACAO_INICIAL:
        baseline["mu"] = np.mean(hi_hist)
        baseline["sigma"] = np.std(hi_hist)
        estado = "Normal"
        print(f"Calibração concluída: μ={baseline['mu']:.3f}, σ={baseline['sigma']:.3f}")

    elif baseline["mu"] is not None:
        # Atualiza ADWIN
        detector.update(hi)

        # Suavização
        hi_suav = suavizar(hi_hist)[-1]
        hi_deriv = hi_suav - suavizar(hi_hist[:-1])[-1] if len(hi_hist) > 1 else 0

        # Aprendizado incremental do modelo TTF
        X = {"hi": hi_suav, "deriv": hi_deriv}
        y = max(0, 1 - hi_suav)
        modelo_TTF.learn_one(X, y)

        # Previsão de tempo para falha e risco
        TTF_estimado = max(1, 1000 * (1 - modelo_TTF.predict_one(X)))
        risco = min(100, max(0, (1 - hi_suav) * 100))

        
        # Estados adaptativos
   
        if getattr(detector, "drift_detected", getattr(detector, "change_detected", False)):
            salvar_drift_evento(hi)
            estado = "Drift"
            print(f"⚠️ Drift detectado no tick {tick} (HI={hi:.3f})")

        elif hi_suav < (baseline["mu"] - 2 * baseline["sigma"]):
            estado = "Falha"
        elif hi_suav > (baseline["mu"] + 2 * baseline["sigma"]):
            estado = "Reparo"
        else:
            estado = "Normal"

        # Atualização adaptativa do baseline
        if estado in ["Normal", "Reparo"]:
            baseline["mu"] = 0.99 * baseline["mu"] + 0.01 * hi_suav
            baseline["sigma"] = 0.99 * baseline["sigma"] + 0.01 * abs(hi_suav - baseline["mu"])

        salvar_metricas([
            datetime.now().isoformat(timespec="seconds"),
            tick,
            round(hi, 5),
            round(hi_suav, 5),
            round(hi_deriv, 5),
            round(TTF_estimado, 2),
            round(risco, 1),
            estado
        ])


    # Checagem de sinalizadores

    if os.path.exists(ARQ_FLAG_RECALIBRAR):
        recalibrar_baseline()
        os.remove(ARQ_FLAG_RECALIBRAR)

    if os.path.exists(ARQ_FLAG_REPARO):
        estado = "Reparo"
        print("Simulação de reparo recebida.")
        os.remove(ARQ_FLAG_REPARO)

    time.sleep(TICK_INTERVAL)
