"""Gera os PNGs do app (PWA) só com a biblioteca padrão.

Desenho (layout v2): a marca de monitor/icons/icone.svg. Fundo azul-noite arredondado,
nó central em degradê #5b7cff -> #a78bfa ligado a três agentes (um ciano #22d3ee, dois
#e2e8f0). O SVG não é gerado aqui: ele vem do handoff de design e é a fonte da marca.
Uso: python tools/gerar_icones.py   (grava monitor/icons/icone-192.png, -512 e -maskable-512)
"""
import struct
import zlib
from pathlib import Path

FUNDO = (11, 31, 58)        # #0b1f3a
CIANO = (34, 211, 238)      # #22d3ee
CLARO = (226, 232, 240)     # #e2e8f0
GRAD_A = (91, 124, 255)     # #5b7cff
GRAD_B = (167, 139, 250)    # #a78bfa
SAIDA = Path(__file__).resolve().parent.parent / "monitor" / "icons"

# Geometria do icone.svg (viewBox 0..100)
CENTRO = (50, 50, 15.5)
AGENTES = [((50, 22.5), CIANO), ((26.25, 63.75), CLARO), ((73.75, 63.75), CLARO)]
R_AGENTE = 7.75
TRACO = 4.0          # stroke-width das ligações
OPAC_TRACO = 0.7     # stroke-opacity


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


def segmento(ax, ay, bx, by, largura):
    dx, dy = bx - ax, by - ay
    comp2 = dx * dx + dy * dy

    def f(x, y):
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / comp2))
        px, py = ax + t * dx, ay + t * dy
        return (x - px) ** 2 + (y - py) ** 2 <= (largura / 2) ** 2
    return f


def camadas(margem):
    """(forma, cor, opacidade) em coordenadas 0..100; `margem` encolhe a marca (maskable)."""
    k = 1 - 2 * margem
    m = lambda v: 100 * margem + v * k
    cx, cy, cr = CENTRO
    grad = lambda x, y: tuple(GRAD_A[i] + (GRAD_B[i] - GRAD_A[i]) *
                              max(0.0, min(1.0, ((x - (m(cx) - cr * k)) + (y - (m(cy) - cr * k))) / (4 * cr * k)))
                              for i in range(3))
    lista = [(ret_arred(0, 0, 100, 100, 0 if margem else 22), FUNDO, 1.0)]
    for (ax, ay), _ in AGENTES:
        lista.append((segmento(m(cx), m(cy), m(ax), m(ay), TRACO * k), CIANO, OPAC_TRACO))
    lista.append((circulo(m(cx), m(cy), cr * k), grad, 1.0))
    for (ax, ay), cor in AGENTES:
        lista.append((circulo(m(ax), m(ay), R_AGENTE * k), cor, 1.0))
    return lista


def png(tamanho, margem, destino):
    formas = camadas(margem)
    passo = 100 / tamanho
    linhas = []
    for py in range(tamanho):
        linha = bytearray([0])
        for px in range(tamanho):
            cor, alfa = [0.0, 0.0, 0.0], 0.0
            for forma, rgb, opac in formas:
                dentro = 0
                for i in range(4):
                    for j in range(4):
                        dentro += forma((px + (i + .5) / 4) * passo, (py + (j + .5) / 4) * passo)
                c = dentro / 16 * opac
                if c:
                    base = rgb((px + .5) * passo, (py + .5) * passo) if callable(rgb) else rgb
                    cor = [cor[i] * (1 - c) + base[i] * c for i in range(3)]
                    alfa = alfa * (1 - c) + c
            linha += bytes([round(v) for v in cor] + [round(alfa * 255)])
        linhas.append(bytes(linha))
    bruto = zlib.compress(b"".join(linhas), 9)

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cab = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 6, 0, 0, 0)
    destino.write_bytes(b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cab) + bloco(b"IDAT", bruto) + bloco(b"IEND", b""))


if __name__ == "__main__":
    SAIDA.mkdir(parents=True, exist_ok=True)
    png(192, 0, SAIDA / "icone-192.png")
    png(512, 0, SAIDA / "icone-512.png")
    png(512, 0.1, SAIDA / "icone-maskable-512.png")
    print("PNGs gravados em", SAIDA)
