"""Gera os gráficos estáticos da comparação com a inflação (IPCA).

Entradas: dados/tratados/composicao_preco_uf.csv, dados/tratados/ipca.csv e as tabelas
de dados/tratados/resultados/ geradas por scripts/03_analisar.py.
Saída: graficos/*.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
TRATADOS = RAIZ / "dados" / "tratados"
SAIDA = RAIZ / "graficos"

# Cada parcela tem sempre a mesma cor, em todos os gráficos.
COR = {"produtor": "#2a78d6", "icms": "#eb6834", "distribuicao": "#1baf7a", "revenda": "#eda100",
       "consumidor": "#4a3aa7", "ipca": "#898781"}
NOME = {"produtor": "Produtor + tributos federais", "icms": "ICMS", "distribuicao": "Margem de distribuição",
        "revenda": "Margem de revenda", "consumidor": "Preço ao consumidor (RS)", "ipca": "IPCA"}
FUNDO, TINTA, SECUNDARIA, GRADE, EIXO = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
FONTE = "Fontes: ANP (composição do preço do P13, republicada pelo Sindigás) e IBGE (IPCA)."

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": EIXO,
                     "axes.labelcolor": SECUNDARIA, "xtick.color": SECUNDARIA, "ytick.color": SECUNDARIA,
                     "figure.facecolor": FUNDO, "axes.facecolor": FUNDO, "savefig.facecolor": FUNDO})


def br(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def base(titulo: str, subtitulo: str, direita: float = 0.97, tamanho=(10, 5.6)):
    fig, ax = plt.subplots(figsize=tamanho)
    fig.subplots_adjust(top=0.78, bottom=0.14, left=0.08, right=direita)
    fig.text(0.08, 0.94, titulo, fontsize=14, fontweight="bold", color=TINTA, ha="left")
    fig.text(0.08, 0.885, subtitulo, fontsize=10, color=SECUNDARIA, ha="left")
    fig.text(0.08, 0.025, FONTE, fontsize=8, color=SECUNDARIA, ha="left")
    for lado in ["top", "right", "left"]:
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    return fig, ax


def grafico_indices() -> None:
    """Preço ao consumidor e preço do produtor contra o IPCA, média de 2018 = 100."""
    comp = pd.read_csv(TRATADOS / "composicao_preco_uf.csv")
    rs = comp[comp["local"] == "Rio Grande do Sul"].pivot_table(index="mes", columns="componente", values="valor")
    ipca = pd.read_csv(TRATADOS / "ipca.csv").set_index("mes")["indice"]
    series = pd.DataFrame({"consumidor": rs["preco_consumidor"], "produtor": rs["produtor_com_tributos_federais"],
                           "ipca": ipca.reindex(rs.index)})
    indice = 100 * series / series.loc["2018-01":"2018-12"].mean()
    x = pd.to_datetime(indice.index + "-01")

    fig, ax = base("O gás subiu mais que a inflação, mas o custo do produto subiu menos",
                   "Preço do botijão de 13 kg no Rio Grande do Sul e IPCA, em índice (média de 2018 = 100)", direita=0.78)
    ax.plot(x, indice["ipca"], color=COR["ipca"], linewidth=2, linestyle=(0, (4, 2)))
    for chave in ["produtor", "consumidor"]:
        ax.plot(x, indice[chave], color=COR[chave], linewidth=2)
    ax.axhline(100, color=EIXO, linewidth=1)
    # Rótulos diretos no fim de cada linha, afastados para não se sobreporem.
    finais = indice.ffill().iloc[-1].sort_values()
    posicoes, minimo = {}, -1e9
    for chave, valor in finais.items():
        posicoes[chave] = max(valor, minimo + 9)
        minimo = posicoes[chave]
    for chave, y in posicoes.items():
        ax.annotate(f"{NOME[chave]}\n{br(finais[chave])}", xy=(x[-1], finais[chave]), xytext=(x[-1] + pd.Timedelta(days=45), y),
                    color=TINTA, fontsize=9, va="center", annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=COR[chave], linewidth=2, shrinkA=0, shrinkB=0))
    ax.set_ylim(80, 260)
    ax.set_xlim(x[0], x[-1])
    fig.savefig(SAIDA / "1_indices_vs_ipca.png", dpi=160)
    plt.close(fig)


def grafico_composicao() -> None:
    """Parcelas do preço por ano, em reais de hoje."""
    t = pd.read_csv(TRATADOS / "resultados" / "composicao_real_anual.csv")
    ordem = ["produtor", "icms", "distribuicao", "revenda"]
    rotulos = [str(a) if m == 12 or a == 2020 else f"{a}\n({m} meses)" for a, m in zip(t["ano"], t["meses"])]
    fig, ax = base("Descontada a inflação, o que cresceu foram o ICMS e a margem de revenda",
                   "Composição do preço do botijão de 13 kg no RS, média anual em reais de ago/2026 (corrigidos pelo IPCA)")
    fundo = pd.Series(0.0, index=t.index)
    for chave in ordem:
        barras = ax.bar(rotulos, t[chave], bottom=fundo, width=0.62, color=COR[chave], edgecolor=FUNDO, linewidth=2, label=NOME[chave])
        for barra, valor in zip(barras, t[chave]):
            ax.text(barra.get_x() + barra.get_width() / 2, barra.get_y() + barra.get_height() / 2, br(valor),
                    ha="center", va="center", fontsize=8.5, color=TINTA)
        fundo += t[chave]
    for i, total in enumerate(fundo):
        ax.text(i, total + 2, f"R$ {br(total)}", ha="center", va="bottom", fontsize=9.5, fontweight="bold", color=TINTA)
    ax.set_ylim(0, 150)
    ax.yaxis.set_major_formatter(lambda v, _: f"R$ {br(v)}")
    manejos, nomes = ax.get_legend_handles_labels()
    ax.legend(manejos, nomes, loc="lower left", bbox_to_anchor=(-0.01, 1.0), ncol=4, frameon=False, fontsize=9, labelcolor=TINTA, columnspacing=1.4, handlelength=1.2)
    fig.savefig(SAIDA / "2_composicao_real_anual.png", dpi=160)
    plt.close(fig)


def grafico_reajustes() -> None:
    """Variação do preço no ano contra o IPCA do ano."""
    t = pd.read_csv(TRATADOS / "resultados" / "reajuste_anual_vs_ipca.csv")
    rotulos = [str(a) if ate.endswith("-12") else f"{a}\n(até {ate[5:]}/{ate[2:4]})" for a, ate in zip(t["ano"], t["ate"])]
    fig, ax = base("Quase toda a alta acima da inflação aconteceu em 2021",
                   "Variação do preço do botijão de 13 kg no RS e do IPCA, de dezembro a dezembro, em %")
    largura, posicoes = 0.36, range(len(t))
    for deslocamento, coluna, chave in [(-largura / 2 - 0.02, "glp_pct", "consumidor"), (largura / 2 + 0.02, "ipca_pct", "ipca")]:
        barras = ax.bar([p + deslocamento for p in posicoes], t[coluna], width=largura, color=COR[chave], label=NOME[chave])
        for barra, valor in zip(barras, t[coluna]):
            ax.text(barra.get_x() + barra.get_width() / 2, valor + (0.8 if valor >= 0 else -0.8), br(valor, 1),
                    ha="center", va="bottom" if valor >= 0 else "top", fontsize=9, color=TINTA)
    ax.axhline(0, color=EIXO, linewidth=1)
    ax.set_xticks(list(posicoes), rotulos)
    ax.set_ylim(-6, 46)
    ax.yaxis.set_major_formatter(lambda v, _: f"{br(v)}%")
    ax.legend(loc="lower left", bbox_to_anchor=(-0.01, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=TINTA, columnspacing=1.4, handlelength=1.2)
    ax.spines["bottom"].set_visible(False)
    fig.savefig(SAIDA / "3_reajuste_anual_vs_ipca.png", dpi=160)
    plt.close(fig)


def main() -> None:
    SAIDA.mkdir(exist_ok=True)
    grafico_indices()
    grafico_composicao()
    grafico_reajustes()
    print("Gráficos gravados em graficos/:", ", ".join(sorted(p.name for p in SAIDA.glob("*.png"))))


if __name__ == "__main__":
    main()
