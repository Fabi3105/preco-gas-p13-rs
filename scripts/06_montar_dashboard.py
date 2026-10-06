"""Monta o painel em um único arquivo HTML, sem dependências externas.

Junta dashboard/modelo.html com os dados (dados.js e projecao.js) e a logomarca.
Saída: dashboard/index.html, que abre direto no navegador e pode ser publicado como está.
"""
from pathlib import Path
import base64

PASTA = Path(__file__).resolve().parent.parent / "dashboard"


def main() -> None:
    html = (PASTA / "modelo.html").read_text(encoding="utf-8")
    html = html.replace("/*__DADOS__*/", (PASTA / "dados.js").read_text(encoding="utf-8"))
    html = html.replace("/*__PROJECAO__*/", (PASTA / "projecao.js").read_text(encoding="utf-8"))
    logo = base64.b64encode((PASTA / "logo-aliatti.png").read_bytes()).decode()
    html = html.replace("__LOGO__", "data:image/png;base64," + logo)
    destino = PASTA / "index.html"
    destino.write_text(html, encoding="utf-8")
    print(f"Gravado dashboard/index.html ({destino.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
