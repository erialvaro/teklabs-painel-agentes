"""Gera os ícones do app (PNG e SVG) só com a biblioteca padrão.

Desenho: quadrado arredondado azul-noite com um "T" ciano e três nós (os agentes).
Uso: python tools/gerar_icones.py   (grava em monitor/icons/)
"""
import struct
import zlib
from pathlib import Path

FUNDO = (11, 31, 58)       # #0b1f3a
DESTAQUE = (34, 211, 238)  # #22d3ee
CLARO = (226, 232, 240)    # #e2e8f0
SAIDA = Path(__file__).resolve().parent.parent / "monitor" / "icons"


def cobertura(px, py, forma, s):
    """Fração (0..1) do pixel coberta pela forma, com 4x4 subamostras."""
    dentro = 0
    for i in range(4):
        for j in range(4):
            x, y = (px + (i + 0.5) / 4) / s, (py + (j + 0.5) / 4) / s
            dentro += forma(x, y)
    return dentro / 16


def ret_arred(x0, y0, x1, y1, r):
    def f(x, y):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        cx = min(max(x, x0 + r), x1 - r)
        cy = min(max(y, y0 + r), y1 - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    return f


def circulo(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def camadas(margem):
    """Coordenadas em 0..1; `margem` encolhe o desenho para a versão maskable."""
    k = 1 - 2 * margem
    m = lambda v: margem + v * k
    return [
        (ret_arred(0, 0, 1, 1, 0.0 if margem else 0.22), FUNDO),
        (ret_arred(m(0.22), m(0.22), m(0.78), m(0.36), 0.035 * k), DESTAQUE),   # barra do T
        (ret_arred(m(0.43), m(0.22), m(0.57), m(0.70), 0.035 * k), DESTAQUE),   # haste do T
        (circulo(m(0.27), m(0.80), 0.065 * k), CLARO),                          # agentes
        (circulo(m(0.50), m(0.84), 0.065 * k), CLARO),
        (circulo(m(0.73), m(0.80), 0.065 * k), CLARO),
    ]


def png(tamanho, margem, destino):
    linhas = []
    formas = camadas(margem)
    for py in range(tamanho):
        linha = bytearray([0])
        for px in range(tamanho):
            cor, alfa = [0.0, 0.0, 0.0], 0.0
            for forma, rgb in formas:
                c = cobertura(px, py, forma, tamanho)
                if c:
                    cor = [cor[i] * (1 - c) + rgb[i] * c for i in range(3)]
                    alfa = alfa * (1 - c) + c
            linha += bytes([round(v) for v in cor] + [round(alfa * 255)])
        linhas.append(bytes(linha))
    bruto = zlib.compress(b"".join(linhas), 9)

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cab = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 6, 0, 0, 0)
    destino.write_bytes(b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cab) + bloco(b"IDAT", bruto) + bloco(b"IEND", b""))


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="22" fill="#0b1f3a"/>
  <rect x="22" y="22" width="56" height="14" rx="3.5" fill="#22d3ee"/>
  <rect x="43" y="22" width="14" height="48" rx="3.5" fill="#22d3ee"/>
  <circle cx="27" cy="80" r="6.5" fill="#e2e8f0"/>
  <circle cx="50" cy="84" r="6.5" fill="#e2e8f0"/>
  <circle cx="73" cy="80" r="6.5" fill="#e2e8f0"/>
</svg>
"""

if __name__ == "__main__":
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "icone.svg").write_text(SVG, encoding="utf-8")
    png(192, 0, SAIDA / "icone-192.png")
    png(512, 0, SAIDA / "icone-512.png")
    png(512, 0.1, SAIDA / "icone-maskable-512.png")
    print("ícones gravados em", SAIDA)
