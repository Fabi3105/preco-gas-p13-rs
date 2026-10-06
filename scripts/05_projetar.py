"""Projeção do preço e do volume de P13 no RS e nas cidades da Serra Gaúcha até dez/2027.

Método, propositalmente simples e conferível:
- Preço no RS: parte da média do último trimestre e reajusta pela inflação, com o IPCA
  repetindo a taxa dos últimos 12 meses. A escolha vem do próprio histórico: fora 2021,
  o botijão andou junto com o IPCA em todos os anos.
- Escolha do método: quatro regras foram testadas em seis pontos do passado (de dez/2022
  a jun/2025), cada uma projetando os 12 meses seguintes. A do IPCA teve o menor erro;
  a de tendência dos últimos 36 meses, o maior. A tabela fica em projecao_teste.csv.
- Faixa: vem dos erros desse teste. Para cada distância no futuro, usa os percentis 10
  e 90 do erro que a regra do IPCA cometeu no passado.
- Cidades da Serra: projeção do RS mais a diferença média de cada cidade em relação ao
  RS nos últimos 12 meses; a faixa soma a variação dessa diferença (percentis 10 e 90
  dos últimos 24 meses).
- Volume de P13 no RS: tendência dos totais de 12 meses, distribuída pelos meses com o
  índice sazonal.

Entradas: dados/tratados/*.csv e dados/tratados/resultados/*.csv (script 03).
Saídas: dados/tratados/resultados/projecao_*.csv e dashboard/projecao.js
"""
from pathlib import Path
import json
import zipfile
import io

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
TRATADOS = RAIZ / "dados" / "tratados"
RESULTADOS = TRATADOS / "resultados"
PAINEL = RAIZ / "dados" / "brutos" / "sindigas" / "painel-dinamico-dados-glp.zip"
FIM = pd.Period("2027-12", freq="M")
JANELA = 36          # meses usados na tendência do volume
SERRA = ["CAXIAS DO SUL", "BENTO GONCALVES", "VACARIA", "GRAMADO"]
ORIGENS_DO_TESTE = ["2022-12", "2023-06", "2023-12", "2024-06", "2024-12", "2025-06"]
FAIXAS_DE_HORIZONTE = [(1, 3), (4, 6), (7, 9), (10, 12), (13, 18)]


def regra_ipca(preco: pd.Series, ipca: pd.Series, origem: pd.Period, h: int) -> float:
    """Média do último trimestre até a origem, reajustada pelo IPCA dos 12 meses anteriores."""
    base = preco[:origem].dropna().iloc[-3:].mean()
    taxa = ipca[origem] / ipca[origem - 12] - 1
    return base * (1 + taxa) ** ((h + 1) / 12)   # o trimestre-base está centrado um mês antes da origem


def regra_tendencia(preco: pd.Series, origem: pd.Period, h: int, janela: int) -> float:
    base = preco[:origem].dropna().iloc[-janela:]
    b, a = np.polyfit(np.arange(len(base)), np.log(base.to_numpy()), 1)
    return float(np.exp(a + b * (len(base) - 1 + h)))


def testar_regras(preco: pd.Series, ipca: pd.Series) -> pd.DataFrame:
    """Aplica cada regra em pontos do passado e mede o erro contra o preço realizado."""
    regras = {
        "ipca": lambda o, h: regra_ipca(preco, ipca, o, h),
        "preco_constante": lambda o, h: preco[:o].dropna().iloc[-3:].mean(),
        "tendencia_12m": lambda o, h: regra_tendencia(preco, o, h, 12),
        "tendencia_36m": lambda o, h: regra_tendencia(preco, o, h, 36),
    }
    linhas = []
    for origem in [pd.Period(o, freq="M") for o in ORIGENS_DO_TESTE]:
        for h in range(1, 19):
            mes = origem + h
            if mes not in preco.index or pd.isna(preco[mes]):
                continue
            for nome, regra in regras.items():
                previsto = regra(origem, h)
                linhas.append({"regra": nome, "origem": str(origem), "horizonte": h, "mes": str(mes),
                               "previsto": previsto, "realizado": preco[mes], "erro_pct": (previsto / preco[mes] - 1) * 100})
    return pd.DataFrame(linhas)


def main() -> None:
    coletas = pd.read_csv(TRATADOS / "coletas_rs.csv")
    ipca = pd.read_csv(TRATADOS / "ipca.csv").set_index("mes")["indice"]
    preco_rs = coletas.groupby("mes")["preco_venda"].mean()
    ultimo = pd.Period(preco_rs.index.max(), freq="M")
    preco_p = preco_rs.copy()
    preco_p.index = pd.PeriodIndex(preco_p.index, freq="M")
    ipca_p = ipca.copy()
    ipca_p.index = pd.PeriodIndex(ipca_p.index, freq="M")

    # --- Teste das regras em pontos do passado ---
    teste = testar_regras(preco_p, ipca_p)
    teste.round(2).to_csv(RESULTADOS / "projecao_teste.csv", index=False, encoding="utf-8")
    ate12 = teste[teste["horizonte"] <= 12]
    comparacao = ate12.groupby("regra")["erro_pct"].agg(erro_medio_abs=lambda e: e.abs().mean(), vies="mean",
                                                       pior_erro_abs=lambda e: e.abs().max()).round(2)
    comparacao = comparacao.sort_values("erro_medio_abs").reset_index()
    comparacao.to_csv(RESULTADOS / "projecao_comparacao_regras.csv", index=False, encoding="utf-8")
    erros_ipca = teste[teste["regra"] == "ipca"]
    # Percentis do erro em cada faixa de distância, ligados por interpolação para a
    # faixa da projeção não dar saltos de um mês para o outro.
    centros, p10, p90 = [], [], []
    for inicio, fim in FAIXAS_DE_HORIZONTE:
        e = erros_ipca[erros_ipca["horizonte"].between(inicio, fim)]["erro_pct"]
        centros.append((inicio + fim) / 2)
        p10.append(e.quantile(0.1))
        p90.append(e.quantile(0.9))
    horizontes = np.arange(1, 19)
    faixa = {int(h): (float(a), float(b)) for h, a, b in
             zip(horizontes, np.interp(horizontes, centros, p10), np.interp(horizontes, centros, p90))}

    # --- Preço no RS ---
    # O IPCA mais recente pode ser posterior ao último preço; a taxa usada é a dos 12 meses mais recentes.
    ipca_12m = ipca.iloc[-1] / ipca.iloc[-13] - 1
    base_preco = preco_rs.iloc[-3:].mean()
    meses = pd.period_range(ultimo + 1, FIM, freq="M")
    proj = pd.DataFrame({"mes": meses.astype(str)})
    passos = np.arange(1, len(meses) + 1)
    proj["central"] = base_preco * (1 + ipca_12m) ** ((passos + 1) / 12)
    # Erro positivo no teste = a regra previu acima do realizado; a faixa corrige nesse sentido.
    proj["minimo"] = [c / (1 + faixa[min(h, 18)][1] / 100) for c, h in zip(proj["central"], passos)]
    proj["maximo"] = [c / (1 + faixa[min(h, 18)][0] / 100) for c, h in zip(proj["central"], passos)]
    proj = proj.round(2)
    proj.to_csv(RESULTADOS / "projecao_preco_rs.csv", index=False, encoding="utf-8")

    # --- Cidades da Serra ---
    mensal = coletas.pivot_table(index="mes", columns="municipio", values="preco_venda", aggfunc="mean")
    diferenca = mensal[SERRA].sub(preco_rs, axis=0)
    linhas = []
    for cidade in SERRA:
        d12, d24 = diferenca[cidade].dropna().iloc[-12:], diferenca[cidade].dropna().iloc[-24:]
        for _, p in proj.iterrows():
            linhas.append({"municipio": cidade, "mes": p["mes"], "central": p["central"] + d12.mean(),
                           "minimo": p["minimo"] + d24.quantile(0.1), "maximo": p["maximo"] + d24.quantile(0.9)})
    serra = pd.DataFrame(linhas).round(2)
    serra.to_csv(RESULTADOS / "projecao_preco_serra.csv", index=False, encoding="utf-8")
    resumo = []
    for cidade in ["RS"] + SERRA:
        atual = (preco_rs if cidade == "RS" else mensal[cidade]).dropna().iloc[-12:].mean()
        fonte = proj if cidade == "RS" else serra[serra["municipio"] == cidade]
        ano = fonte[fonte["mes"].str.startswith("2027")]
        fim = fonte[fonte["mes"] == str(FIM)].iloc[0]
        resumo.append({"local": cidade, "media_ultimos_12m": atual, "media_2027": ano["central"].mean(),
                       "dez_2027": fim["central"], "dez_2027_min": fim["minimo"], "dez_2027_max": fim["maximo"],
                       "diferenca_para_rs": 0.0 if cidade == "RS" else diferenca[cidade].dropna().iloc[-12:].mean()})
    resumo = pd.DataFrame(resumo).round(2)
    resumo.to_csv(RESULTADOS / "projecao_resumo.csv", index=False, encoding="utf-8")

    # --- Série histórica mensal das cidades da Serra, para o gráfico ---
    historico = mensal[SERRA].assign(RS=preco_rs).round(2).reset_index()
    historico.to_csv(RESULTADOS / "preco_mensal_serra.csv", index=False, encoding="utf-8")

    # --- Volume de P13 no RS ---
    vendas = pd.read_csv(TRATADOS / "vendas_p13_rs.csv")
    vendas["mes"] = vendas["ano"].astype(str) + "-" + vendas["mes_do_ano"].astype(str).str.zfill(2)
    v = vendas.set_index("mes")["mil_ton"]
    soma12 = v.rolling(12).sum().dropna()
    t = np.arange(len(soma12.iloc[-JANELA:]), dtype=float)
    b, a = np.polyfit(t, np.log(soma12.iloc[-JANELA:].to_numpy()), 1)
    taxa_volume = np.exp(12 * b) - 1
    sazonal = pd.read_csv(RESULTADOS / "sazonalidade_volume.csv").set_index("mes_do_ano")["indice"] / 100
    sazonal = sazonal / sazonal.mean()
    ultimo_v = pd.Period(v.index.max(), freq="M")
    nivel = soma12.iloc[-1] / 12                 # média mensal dos últimos 12 meses, centrada 5,5 meses atrás
    futuros = pd.period_range(ultimo_v + 1, FIM, freq="M")
    volume = pd.DataFrame({"mes": futuros.astype(str)})
    passos_v = np.arange(1, len(futuros) + 1) + 5.5
    volume["mil_ton"] = [nivel * (1 + taxa_volume) ** (p / 12) * sazonal.loc[int(m.month)] for p, m in zip(passos_v, futuros)]
    volume = volume.round(3)
    volume.to_csv(RESULTADOS / "projecao_volume_rs.csv", index=False, encoding="utf-8")
    anual = pd.concat([v.rename("mil_ton").reset_index().assign(tipo="realizado"), volume.assign(tipo="projetado")])
    anual["ano"] = anual["mes"].str[:4].astype(int)
    volume_anual = anual.pivot_table(index="ano", columns="tipo", values="mil_ton", aggfunc="sum").fillna(0)
    volume_anual["total"] = volume_anual.sum(axis=1)
    volume_anual = volume_anual.round(1).reset_index()
    volume_anual.to_csv(RESULTADOS / "projecao_volume_anual.csv", index=False, encoding="utf-8")

    # --- Tamanho do mercado: botijões vendidos x preço médio ao consumidor ---
    def mercado(ano: int, preco: float, mil_ton: float) -> dict:
        botijoes = mil_ton * 1e6 / 13
        return {"ano": ano, "mil_ton": round(mil_ton, 1), "botijoes_milhoes": round(botijoes / 1e6, 2),
                "preco_medio": round(preco, 2), "faturamento_bilhoes": round(botijoes * preco / 1e9, 2)}
    preco_ano = preco_rs.groupby(preco_rs.index.str[:4]).mean()
    vol_total = volume_anual.set_index("ano")["total"]
    preco_2026 = pd.concat([preco_rs[preco_rs.index.str.startswith("2026")], proj.set_index("mes")["central"].loc["2026-07":"2026-12"]]).mean()
    tamanho = pd.DataFrame([mercado(2025, preco_ano["2025"], vol_total[2025]),
                            mercado(2026, preco_2026, vol_total[2026]),
                            mercado(2027, proj[proj["mes"].str.startswith("2027")]["central"].mean(), vol_total[2027])])
    tamanho.to_csv(RESULTADOS / "projecao_mercado.csv", index=False, encoding="utf-8")

    # --- Participação do P13 no volume de GLP do RS ---
    partes = []
    with zipfile.ZipFile(PAINEL) as z:
        for nome in ["GLP_Vendas_Historico.csv", "GLP_Vendas_Atual.csv"]:
            df = pd.read_csv(io.BytesIO(z.read(nome)), sep=";", encoding="latin1", dtype=str)
            df = df.rename(columns={"UF de Destino": "UF Destino"})
            partes.append(df[["Ano", "UF Destino", "Código de Embalagem GLP", "Quantidade de Produto(mil ton)"]])
    emb = pd.concat(partes).set_axis(["ano", "uf", "embalagem", "mil_ton"], axis=1)
    emb["mil_ton"] = pd.to_numeric(emb["mil_ton"].str.replace(",", ".", regex=False))
    emb = emb[(emb["uf"] == "RS") & (emb["ano"].astype(int) >= 2018)]
    emb["grupo"] = np.where(emb["embalagem"].str.replace(" ", "") == "P13", "p13",
                            np.where(emb["embalagem"].str.contains("Granel", case=False), "granel", "outros_recipientes"))
    participacao = emb.pivot_table(index="ano", columns="grupo", values="mil_ton", aggfunc="sum").round(1)
    participacao["p13_pct"] = (100 * participacao["p13"] / participacao.sum(axis=1)).round(1)
    participacao = participacao.reset_index()
    participacao.to_csv(RESULTADOS / "participacao_p13.csv", index=False, encoding="utf-8")

    saida = {
        "preco_rs": json.loads(proj.to_json(orient="records")),
        "preco_serra": json.loads(serra.to_json(orient="records")),
        "historico_serra": json.loads(historico.to_json(orient="records")),
        "resumo": json.loads(resumo.to_json(orient="records")),
        "comparacao_regras": json.loads(comparacao.to_json(orient="records")),
        "volume": json.loads(volume.to_json(orient="records")),
        "volume_anual": json.loads(volume_anual.to_json(orient="records")),
        "mercado": json.loads(tamanho.to_json(orient="records")),
        "participacao_p13": json.loads(participacao.to_json(orient="records")),
        "premissas": {
            "ultimo_mes_preco": str(ultimo), "ultimo_mes_volume": str(ultimo_v), "horizonte": str(FIM),
            "preco_base": round(float(base_preco), 2), "ipca_12m_pct": round(float(ipca_12m * 100), 2),
            "ultimo_mes_ipca": str(ipca.index[-1]), "taxa_anual_volume_pct": round(float(taxa_volume * 100), 2),
            "origens_do_teste": ORIGENS_DO_TESTE,
            "erro_medio_abs_regra_ipca_pct": float(comparacao.set_index("regra").loc["ipca", "erro_medio_abs"]),
        },
    }
    (RAIZ / "dashboard" / "projecao.js").write_text("const PROJECAO = " + json.dumps(saida, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(json.dumps(saida["premissas"], ensure_ascii=False, indent=1))
    print(comparacao.to_string(index=False))
    print(resumo.to_string(index=False))
    print(tamanho.to_string(index=False))
    print(volume_anual.tail(3).to_string(index=False))
    print(participacao.to_string(index=False))


if __name__ == "__main__":
    main()
