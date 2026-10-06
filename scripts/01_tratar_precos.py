"""Lê os CSVs semestrais da ANP e gera as bases tratadas de preços.

Entrada: dados/brutos/anp/*.csv (Série Histórica de Preços de Combustíveis e de GLP)
Saídas, em dados/tratados/:
- coletas_rs.csv: uma linha por revenda e data de coleta no Rio Grande do Sul;
- preco_mensal_uf.csv: preço médio mensal ao consumidor por UF e para o Brasil.

Tratamentos:
- padroniza nomes de colunas, datas e números (vírgula decimal);
- remove linhas exatamente duplicadas;
- cria `mes` (AAAA-MM) e `tipo_bandeira` (BRANCA ou BANDEIRADA);
- cria `margem` (venda menos compra) quando o preço de compra existe (até ago/2020).
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados" / "brutos" / "anp"
TRATADOS = RAIZ / "dados" / "tratados"
UF_ESTUDO = "RS"

COLUNAS = {
    "Estado - Sigla": "uf",
    "Municipio": "municipio",
    "Revenda": "revenda",
    "CNPJ da Revenda": "cnpj",
    "Bairro": "bairro",
    "Data da Coleta": "data",
    "Valor de Venda": "preco_venda",
    "Valor de Compra": "preco_compra",
    "Bandeira": "bandeira",
}


def ler(arquivo: Path) -> pd.DataFrame:
    df = pd.read_csv(arquivo, sep=";", encoding="utf-8-sig", dtype=str)
    faltando = set(COLUNAS) - set(df.columns)
    if faltando:
        raise ValueError(f"{arquivo.name}: colunas ausentes {faltando}")
    if set(df["Produto"].unique()) != {"GLP"} or set(df["Unidade de Medida"].unique()) != {"R$ / 13 kg"}:
        raise ValueError(f"{arquivo.name}: produto ou unidade inesperados")
    return df[list(COLUNAS)].rename(columns=COLUNAS)


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def main() -> None:
    arquivos = sorted(BRUTOS.glob("*.csv"))
    df = pd.concat([ler(a) for a in arquivos], ignore_index=True)
    lidas = len(df)

    for coluna in ["municipio", "revenda", "cnpj", "bairro", "bandeira"]:
        df[coluna] = df[coluna].str.strip()
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    for coluna in ["preco_venda", "preco_compra"]:
        df[coluna] = pd.to_numeric(df[coluna].str.replace(",", ".", regex=False))
    df = df.drop_duplicates(subset=["cnpj", "data", "preco_venda", "preco_compra", "bandeira"])

    df["mes"] = df["data"].dt.strftime("%Y-%m")
    df["tipo_bandeira"] = df["bandeira"].where(df["bandeira"] == "BRANCA", "BANDEIRADA")
    df["margem"] = (df["preco_venda"] - df["preco_compra"]).round(2)

    TRATADOS.mkdir(parents=True, exist_ok=True)

    def resumo(grupo):
        return grupo.agg(coletas=("preco_venda", "size"), revendas=("cnpj", "nunique"),
                         municipios=("municipio", "nunique"), preco_medio=("preco_venda", "mean"),
                         preco_mediano=("preco_venda", "median"))

    por_uf = resumo(df.groupby(["uf", "mes"])).reset_index()
    brasil = resumo(df.assign(municipio=df["uf"] + "/" + df["municipio"]).groupby("mes")).reset_index()
    brasil.insert(0, "uf", "BR")
    mensal = pd.concat([brasil, por_uf], ignore_index=True).round({"preco_medio": 2, "preco_mediano": 2})
    mensal.to_csv(TRATADOS / "preco_mensal_uf.csv", index=False, encoding="utf-8")

    rs = df[df["uf"] == UF_ESTUDO].drop(columns="uf").sort_values(["data", "municipio", "cnpj"])
    rs.to_csv(TRATADOS / "coletas_rs.csv", index=False, encoding="utf-8", date_format="%Y-%m-%d")

    print(f"{len(arquivos)} arquivos, {milhar(lidas)} linhas lidas, {milhar(lidas - len(df))} duplicadas removidas")
    print(f"Período: {df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y}")
    print(f"Preço de venda no país: de R$ {df['preco_venda'].min():.2f} a R$ {df['preco_venda'].max():.2f}")
    com_compra = df["preco_compra"].notna()
    print(f"Linhas com preço de compra: {milhar(int(com_compra.sum()))}, a última em {df.loc[com_compra, 'data'].max():%d/%m/%Y}")
    print(f"preco_mensal_uf.csv: {milhar(len(mensal))} linhas")
    print(f"coletas_rs.csv: {milhar(len(rs))} linhas, {rs['municipio'].nunique()} municípios, {rs['cnpj'].nunique()} revendas")


if __name__ == "__main__":
    main()
