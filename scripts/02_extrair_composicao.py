"""Extrai a composição do preço do P13 por estado das tabelas em PDF.

Fonte: tabelas "Evolução dos preços de GLP (R$ / botijão de 13 kg)", elaboradas pela
ANP (Superintendência de Defesa da Concorrência) e republicadas pelo Sindigás, uma por ano.
Cada tabela traz, para o Brasil e para cada UF, nove linhas por mês: do preço do produtor
ao preço final ao consumidor, passando por tributos e margens de distribuição e revenda.

Saída: dados/tratados/composicao_preco_uf.csv (formato longo: local, mes, componente, valor).
Requer o utilitário pdftotext (Poppler).
"""
from pathlib import Path
import re
import subprocess
import unicodedata

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PDFS = RAIZ / "dados" / "brutos" / "sindigas"
SAIDA = RAIZ / "dados" / "tratados" / "composicao_preco_uf.csv"

# Ordem em que as linhas aparecem em cada bloco. O rótulo mais longo vem antes
# porque "Preço de Distribuição" também aparece dentro de outros rótulos.
COMPONENTES = [
    ("Preço do Produtor s/ ICMS c/ CIDE/PIS/COFINS", "produtor_com_tributos_federais"),
    ("Preço de Realização do Produtor", "produtor"),
    ("Margem Bruta de Distribuição", "margem_distribuicao"),
    ("Margem Bruta de Revenda", "margem_revenda"),
    ("Preço Final ao Consumidor", "preco_consumidor"),
    ("Preço de Distribuição", "preco_distribuicao"),
    ("PIS/COFINS", "pis_cofins"),
    ("CIDE", "cide"),
    ("ICMS", "icms"),
]
LOCAIS = [
    "Brasil", "Acre", "Alagoas", "Amapá", "Amazonas", "Bahia", "Ceará", "Distrito Federal",
    "Espírito Santo", "Goiás", "Maranhão", "Mato Grosso", "Mato Grosso do Sul", "Minas Gerais",
    "Pará", "Paraíba", "Paraná", "Pernambuco", "Piauí", "Rio de Janeiro", "Rio Grande do Norte",
    "Rio Grande do Sul", "Rondônia", "Roraima", "Santa Catarina", "São Paulo", "Sergipe", "Tocantins",
]
MESES = {m: i for i, m in enumerate("jan fev mar abr mai jun jul ago set out nov dez".split(), 1)}
RE_MES = re.compile(r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/(\d{2})\b")
# Um valor é "-" (sem dado), um número, ou um número negativo entre parênteses, como "(0,32)".
# Um "(2)" depois do número é chamada de nota de rodapé e é ignorado.
RE_VALOR = re.compile(r"(?<![\w,(])(-|\(\d{1,3},\d{1,2}\)|\d{1,3}(?:,\d{1,2})?)(?:\s*\(\d\))?(?=\s|$)")


def converter(bruto: str):
    if bruto == "-":
        return None
    if bruto.startswith("("):
        return -float(bruto.strip("()").replace(",", "."))
    return float(bruto.replace(",", "."))


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def ler_pdf(caminho: Path) -> list[dict]:
    texto = subprocess.run(["pdftotext", "-layout", str(caminho), "-"], capture_output=True, text=True, check=True).stdout
    meses: list[str] = []
    blocos: list[dict] = []
    atual: dict = {}
    for linha in texto.splitlines():
        achados = RE_MES.findall(linha)
        if len(achados) >= 3:
            meses = [f"20{aa}-{MESES[m]:02d}" for m, aa in achados]
            continue
        for rotulo, chave in COMPONENTES:
            # Última ocorrência: em algumas linhas o rótulo "ICMS" aparece antes,
            # dentro de "(alíquota de ICMS do produtor)".
            pos = linha.rfind(rotulo)
            if pos < 0:
                continue
            # Chamadas de nota em sobrescrito (¹ ² ³) são descartadas.
            resto = re.sub("[¹²³*]", " ", linha[pos + len(rotulo):])
            brutos = RE_VALOR.findall(resto)
            # Linha de dados: depois do rótulo só há valores. Notas de rodapé que
            # citam "ICMS" ou "PIS/COFINS" têm texto e são ignoradas.
            if not brutos or RE_VALOR.sub("", resto).strip():
                break
            valores = [converter(v) for v in brutos]
            if len(valores) != len(meses):
                raise ValueError(f"{caminho.name}: {len(valores)} valores para {len(meses)} meses em '{linha.strip()[:80]}'")
            if chave in atual:
                raise ValueError(f"{caminho.name}: componente repetido no bloco: {chave}")
            atual[chave] = dict(zip(meses, valores))
            if chave == "preco_consumidor":  # última linha do bloco
                blocos.append(atual)
                atual = {}
            break
    if len(blocos) != len(LOCAIS) or any(len(b) != len(COMPONENTES) for b in blocos):
        raise ValueError(f"{caminho.name}: esperava {len(LOCAIS)} blocos completos, encontrei {len(blocos)}")
    # As tabelas listam o Brasil e depois as UFs em ordem alfabética. Conferimos a
    # ordem pela presença do nome de cada UF no texto, na mesma sequência.
    plano = sem_acento(texto)
    posicao = 0
    for local in LOCAIS:
        achou = re.search(r"(?<![a-z])" + re.escape(sem_acento(local)) + r"(?! do (sul|norte))(?![a-z])", plano[posicao:])
        if not achou:
            raise ValueError(f"{caminho.name}: não encontrei '{local}' na ordem esperada")
        posicao += achou.end()
    linhas = []
    for local, bloco in zip(LOCAIS, blocos):
        for chave, serie in bloco.items():
            for mes, valor in serie.items():
                linhas.append({"local": local, "mes": mes, "componente": chave, "valor": valor})
    return linhas


def main() -> None:
    linhas = []
    for pdf in sorted(PDFS.glob("*-margens-p13-tabela.pdf")):
        parte = ler_pdf(pdf)
        linhas += parte
        print(f"{pdf.name}: {len(parte)} valores")
    df = pd.DataFrame(linhas)
    larga = df.pivot_table(index=["local", "mes"], columns="componente", values="valor", aggfunc="first")
    # Conferência: as parcelas precisam fechar com os preços (tolerância de arredondamento).
    d1 = (larga["preco_distribuicao"] + larga["margem_revenda"] - larga["preco_consumidor"]).abs()
    d2 = (larga["produtor_com_tributos_federais"] + larga["icms"] + larga["margem_distribuicao"] - larga["preco_distribuicao"]).abs()
    print(f"Conferência das somas: {len(larga)} pares local-mês; "
          f"diferença > R$ 0,05 em {int((d1 > 0.05).sum())} (revenda) e {int((d2 > 0.05).sum())} (distribuição)")
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"Gravado {SAIDA.relative_to(RAIZ)}: {len(df)} linhas, {df['mes'].min()} a {df['mes'].max()}")


if __name__ == "__main__":
    main()
