"""Roda as consultas SQL do estudo e grava os resultados.

Entradas: dados/tratados/*.csv (scripts 01 e 02), o painel de vendas do Sindigás (zip)
e o número-índice do IPCA (IBGE).
Saídas:
- dados/tratados/vendas_p13_rs.csv: vendas mensais de P13 com destino ao RS;
- dados/tratados/ipca.csv: número-índice mensal do IPCA;
- dados/tratados/resultados/<consulta>.csv: uma tabela por consulta de sql/consultas.sql;
- dashboard/dados.js: os mesmos resultados, para o painel em HTML.
"""
from pathlib import Path
import io
import json
import re
import sqlite3
import zipfile

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
TRATADOS = RAIZ / "dados" / "tratados"
PAINEL = RAIZ / "dados" / "brutos" / "sindigas" / "painel-dinamico-dados-glp.zip"
CONSULTAS = RAIZ / "sql" / "consultas.sql"
IPCA = RAIZ / "dados" / "brutos" / "ibge" / "ipca_numero_indice.json"
ANO_INICIAL = 2018


def vendas_p13_rs() -> pd.DataFrame:
    """Vendas de P13 das distribuidoras com destino ao RS, por mês, em mil toneladas."""
    colunas = {"Ano": "ano", "Mês": "mes_do_ano", "UF Destino": "uf", "UF de Destino": "uf",
               "Código de Embalagem GLP": "embalagem", "Quantidade de Produto(mil ton)": "mil_ton"}
    partes = []
    with zipfile.ZipFile(PAINEL) as z:
        for nome in ["GLP_Vendas_Historico.csv", "GLP_Vendas_Atual.csv"]:
            df = pd.read_csv(io.BytesIO(z.read(nome)), sep=";", encoding="latin1", dtype=str)
            partes.append(df.rename(columns=colunas)[["ano", "mes_do_ano", "uf", "embalagem", "mil_ton"]])
    df = pd.concat(partes, ignore_index=True)
    df["mil_ton"] = pd.to_numeric(df["mil_ton"].str.replace(",", ".", regex=False))
    df[["ano", "mes_do_ano"]] = df[["ano", "mes_do_ano"]].astype(int)
    filtro = (df["uf"] == "RS") & (df["embalagem"].str.replace(" ", "") == "P13") & (df["ano"] >= ANO_INICIAL)
    return df[filtro].groupby(["ano", "mes_do_ano"], as_index=False)["mil_ton"].sum().round(3)


def ipca() -> pd.DataFrame:
    """Número-índice mensal do IPCA (SIDRA 1737). A primeira linha do JSON é o cabeçalho."""
    linhas = json.loads(IPCA.read_text(encoding="utf-8"))[1:]
    df = pd.DataFrame({"mes": [f"{l['D3C'][:4]}-{l['D3C'][4:]}" for l in linhas],
                       "indice": [pd.to_numeric(l["V"], errors="coerce") for l in linhas]})
    return df.dropna().sort_values("mes").reset_index(drop=True)


def ler_consultas() -> dict[str, str]:
    blocos = re.split(r"^-- nome:\s*(\w+)\s*$", CONSULTAS.read_text(encoding="utf-8"), flags=re.M)
    return {nome: sql.strip() for nome, sql in zip(blocos[1::2], blocos[2::2])}


def main() -> None:
    coletas = pd.read_csv(TRATADOS / "coletas_rs.csv")
    vendas = vendas_p13_rs()
    vendas.to_csv(TRATADOS / "vendas_p13_rs.csv", index=False, encoding="utf-8")

    con = sqlite3.connect(":memory:")
    coletas.to_sql("coletas_rs", con, index=False)
    pd.read_csv(TRATADOS / "preco_mensal_uf.csv").to_sql("preco_mensal_uf", con, index=False)
    pd.read_csv(TRATADOS / "composicao_preco_uf.csv").to_sql("composicao", con, index=False)
    vendas.to_sql("vendas_p13_rs", con, index=False)
    inflacao = ipca()
    inflacao.to_csv(TRATADOS / "ipca.csv", index=False, encoding="utf-8")
    inflacao.to_sql("ipca", con, index=False)

    ultimo_mes = pd.Period(coletas["mes"].max(), freq="M")
    inicio_12m = str(ultimo_mes - 11)
    resultados = {}
    pasta = TRATADOS / "resultados"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, sql in ler_consultas().items():
        parametros = {"inicio_12m": inicio_12m} if ":inicio_12m" in sql else {}
        tabela = pd.read_sql_query(sql, con, params=parametros)
        tabela.to_csv(pasta / f"{nome}.csv", index=False, encoding="utf-8")
        resultados[nome] = json.loads(tabela.to_json(orient="records"))
        print(f"{nome}: {len(tabela)} linhas")

    # Percentis não existem no SQLite: a dispersão dentro de cada município sai do pandas.
    janela = coletas[coletas["mes"] >= inicio_12m]
    dispersao = janela.groupby("municipio")["preco_venda"].quantile([0.1, 0.5, 0.9]).unstack().round(2)
    dispersao.columns = ["p10", "mediana", "p90"]
    dispersao = dispersao.reset_index()
    dispersao.to_csv(pasta / "dispersao_municipios_12m.csv", index=False, encoding="utf-8")
    resultados["dispersao_municipios_12m"] = json.loads(dispersao.to_json(orient="records"))

    resultados["meta"] = {
        "periodo_precos": [coletas["mes"].min(), coletas["mes"].max()],
        "janela_12m": [inicio_12m, str(ultimo_mes)],
        "coletas_rs": int(len(coletas)),
        "municipios_rs": int(coletas["municipio"].nunique()),
        "revendas_rs": int(coletas["cnpj"].nunique()),
        "preco_medio_rs_12m": round(float(janela["preco_venda"].mean()), 2),
    }
    destino = RAIZ / "dashboard" / "dados.js"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("const DADOS = " + json.dumps(resultados, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Janela dos últimos 12 meses: {inicio_12m} a {ultimo_mes}")
    print(f"Gravado {destino.relative_to(RAIZ)} ({destino.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
