import os
import time
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

ARQ_METRICAS = "metricas_hi_ttf.csv"
ARQ_DRIFT = "metricas_drift.csv"
REFRESH = 2  # segundos
RISCO_ALERTA = 70  # %

st.set_page_config(page_title="EdgePHM v4 – Painel", layout="wide")
st.title("EdgePHM v4 — Aprendizado Contínuo com Risco de Falha (%)")


# Barra superior de ações

colA, colB, colC, colD = st.columns(4)
if colA.button(" Recalibrar baseline"):
    open("recalibrar.flag", "w").close()
    st.toast("Recalibração solicitada ao nó de borda.", icon="♻️")
if colB.button(" Simular reparo"):
    open("reparo.flag", "w").close()
    st.toast("Reparo simulado solicitado.", icon="🛠️")
auto_scroll = colC.toggle("Auto-atualizar", value=True)
colD.caption("v4 painel")

placeholder = st.empty()

def carregar_metricas():
    try:
        df = pd.read_csv(ARQ_METRICAS)
        # compatibilidade de nomes (v5 escreve risco_falha)
        if "risco_falha" not in df.columns:
            df["risco_falha"] = (1 - df["HI_suav"]).clip(0, 1) * 100.0
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        return df
    except Exception:
        return pd.DataFrame()

def carregar_drifts():
    try:
        d = pd.read_csv(ARQ_DRIFT)
        if "timestamp" in d.columns:
            d["timestamp"] = pd.to_datetime(d["timestamp"], errors="coerce")
        return d
    except Exception:
        return pd.DataFrame(columns=["timestamp","HI"])

def grafico_hi(df, df_drift):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["HI_suav"], mode="lines",
        name="HI suavizado", line=dict(width=2, color="#00cc96")
    ))
    # pintar estados como pontos
    cores = {"Normal":"#00cc96","Drift":"#ffa15a","Falha":"#ef553b","Reparo":"#636efa","Calibrando":"#2ca02c","Recalibrando":"#19d3f3"}
    if "estado" in df.columns:
        for est, cor in cores.items():
            sub = df[df["estado"]==est]
            if len(sub):
                fig.add_trace(go.Scatter(
                    x=sub["timestamp"], y=sub["HI_suav"], mode="markers",
                    marker=dict(size=6, color=cor), name=est
                ))
    # marcadores de drift
    if len(df_drift):
        yvals = []
        # alinhar HI dos drifts com HI mais próximo temporalmente
        for t in df_drift["timestamp"]:
            idx = df["timestamp"].sub(t).abs().idxmin()
            yvals.append(df.loc[idx, "HI_suav"])
        fig.add_trace(go.Scatter(
            x=df_drift["timestamp"], y=yvals,
            mode="markers", name=" Drift",
            marker=dict(size=10, color="orange", symbol="x")
        ))
    fig.update_layout(
        title="Evolução do Health Index (HI)",
        xaxis_title="Tempo", yaxis_title="HI",
        yaxis=dict(range=[0,1.05]), template="plotly_white", height=380
    )
    return fig

def gauge_risco(valor_atual, valor_anterior=None):
    delta = None
    if valor_anterior is not None:
        delta = dict(reference=valor_anterior, valueformat=".1f", increasing={'color':'#ef553b'}, decreasing={'color':'#00cc96'})
    steps = [
        {'range': [0, 40], 'color': '#E8F7EF'},
        {'range': [40, 70], 'color': '#FFF5E6'},
        {'range': [70, 100], 'color': '#FDE9E7'},
    ]
    fig = go.Figure(go.Indicator(
        mode="gauge+number" if delta is None else "gauge+number+delta",
        value=float(valor_atual),
        delta=delta,
        number={'suffix': "%"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': '#636efa'},
            'steps': steps,
            'threshold': {'line': {'color': '#ef553b', 'width': 3}, 'thickness': 0.8, 'value': RISCO_ALERTA}
        },
        title={'text': "Risco de Falha (%)"}
    ))
    fig.update_layout(height=300, margin=dict(l=10,r=10,t=40,b=10), template="plotly_white")
    return fig

def grafico_ttf(df):
    fig = go.Figure(go.Scatter(
        x=df["timestamp"], y=df["TTF_estimado"], mode="lines",
        name="TTF estimado", line=dict(width=2)
    ))
    fig.update_layout(
        title="Tempo Estimado até Falha (TTF)",
        xaxis_title="Tempo", yaxis_title="TTF (s)",
        template="plotly_white", height=300
    )
    return fig

def info_cards(df):
    ult = df.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", str(ult.get("estado","-")))
    c2.metric("HI (suav)", f"{float(ult['HI_suav']):.3f}")
    c3.metric("TTF (s)", f"{float(ult['TTF_estimado']):.1f}")
    c4.metric("Risco (%)", f"{float(ult['risco_falha']):.1f}")

while True:
    df = carregar_metricas()
    df_drift = carregar_drifts()

    if df.empty:
        st.info("Aguardando geração de métricas pelo nó de borda (metricas_hi_ttf.csv)...")
        if not auto_scroll: break
        time.sleep(REFRESH)
        continue

    df = df.tail(600).reset_index(drop=True)
    ult = df.iloc[-1]
    risco_atual = float(ult["risco_falha"])
    risco_prev = float(df.iloc[-2]["risco_falha"]) if len(df) > 1 else None

    with placeholder.container():
        info_cards(df)

        # chave dinâmica para evitar conflito
        chave = str(int(time.time()))

        # configuração padrão moderna do Plotly
        cfg = {"responsive": True, "displaylogo": False, "displayModeBar": True}

        # linha 1: gauge + TTF
        g1, g2 = st.columns([1, 1])
        g1.plotly_chart(
            gauge_risco(risco_atual, risco_prev),
            key=f"grafico_gauge_{chave}",
            config=cfg
        )
        g2.plotly_chart(
            grafico_ttf(df),
            key=f"grafico_ttf_{chave}",
            config=cfg
        )

        # alerta visual
        if risco_atual >= RISCO_ALERTA:
            st.error(f"Risco elevado de falha ({risco_atual:.1f}%). Avaliar condição e considerar intervenção.")

        # linha 2: HI + tabela
        h1 = st.container()
        h1.plotly_chart(
            grafico_hi(df, df_drift),
            key=f"grafico_hi_{chave}",
            config=cfg
        )

        st.markdown("### Últimas leituras agregadas (métricas da borda)")
        st.dataframe(df.tail(20), use_container_width=True)


    if not auto_scroll:
        break
    time.sleep(REFRESH)
