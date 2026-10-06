"""Baixa os dados públicos usados no estudo.

Fontes:
- ANP, Série Histórica de Preços de Combustíveis e de GLP (um CSV por semestre)
- Sindigás, página "Dados ANP" (vendas, consumo aparente e margens por estado)
- IBGE, SIDRA tabela 1737: número-índice mensal do IPCA

Uso:  python scripts/baixar_dados.py
Só usa a biblioteca padrão do Python. Arquivos já baixados são pulados.
"""
from pathlib import Path
import time
import urllib.parse
import urllib.request

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados" / "brutos"

ANP = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/glp/"
# Nomes exatamente como publicados pela ANP (dois semestres fogem do padrão).
ARQUIVOS_ANP = [
    "glp-2018-01.csv", "glp-2018-02.csv", "glp-2019-01.csv", "glp-2019-02.csv",
    "glp-2020-01.csv", "glp-2020-02.csv", "precos-semestrais-glp2021-01.csv", "glp-2021-02.csv",
    "precos-semestrais-glp-2022-01.csv", "glp-2022-02.csv", "glp-2023-01.csv", "glp-2023-02.csv",
    "glp-2024-01.csv", "glp-2024-02.csv", "glp-2025-01.csv", "glp-2025-02.csv", "glp-2026-01.csv",
]

SINDIGAS = "https://www.sindigas.org.br/Download/DADOS-ESTATISTICOS/"
# O Sindigás usa dois padrões de nome para as tabelas de margem (até 2024 e a partir de 2025).
ARQUIVOS_SINDIGAS = (
    ["relatorio-vendas-recipiente.xlsx", "painel-dinamico-dados-glp.zip"]
    + [f"MARGEM/Margens Rev e Distr por estado {ano} P13 Tabela.pdf" for ano in range(2018, 2025)]
    + [f"MARGEM/{ano}-margens-p13-tabela.pdf" for ano in range(2025, 2027)]
)
TENTATIVAS = 3

# IPCA, número-índice (base dez/1993 = 100), de dez/2017 em diante.
IPCA = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/201712-203012?formato=json"


def baixar(url: str, destino: Path) -> str:
    if destino.exists() and destino.stat().st_size > 0:
        return "já existe"
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/?=&"), headers={"User-Agent": "Mozilla/5.0"})
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                dados = resp.read()
            break
        except Exception as erro:  # rede, 404 etc.
            if tentativa == TENTATIVAS:
                return f"FALHOU ({erro})"
            time.sleep(5 * tentativa)
    if dados[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        return "FALHOU (o servidor devolveu uma página, não o arquivo)"
    destino.write_bytes(dados)
    return f"ok, {len(dados) / 1e6:.1f} MB"


def main() -> None:
    falhas = 0
    tarefas = [(ANP + n, BRUTOS / "anp" / n) for n in ARQUIVOS_ANP]
    for n in ARQUIVOS_SINDIGAS:
        ano = next((p for p in Path(n).stem.replace("-", " ").split() if p.isdigit()), None)
        nome = f"{ano}-margens-p13-tabela.pdf" if n.startswith("MARGEM/") else Path(n).name
        tarefas.append((SINDIGAS + n, BRUTOS / "sindigas" / nome))
    tarefas.append((IPCA, BRUTOS / "ibge" / "ipca_numero_indice.json"))
    for url, destino in tarefas:
        resultado = baixar(url, destino)
        falhas += resultado.startswith("FALHOU")
        print(f"{destino.relative_to(RAIZ)}: {resultado}")
    print(f"\nConcluído: {len(tarefas) - falhas} de {len(tarefas)} arquivos disponíveis em dados/brutos.")
    if falhas:
        print("Rode de novo para tentar os que falharam.")


if __name__ == "__main__":
    main()
