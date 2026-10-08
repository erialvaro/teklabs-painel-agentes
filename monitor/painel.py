"""Painel local dos times de agentes.

Só lê arquivos. Nada é criado, alterado ou travado dentro de .claude/projects.
Única escrita do painel: o arquivo endereco.txt ao lado deste script.

Dois formatos de time são lidos:
  * agentes avulsos (ferramenta Agent): <sessao>/subagents/agent-<id>.jsonl
    + agent-<id>.meta.json, conclusão lida na conversa do gerente <sessao>.jsonl.
    Formato conferido em disco em 30/09/2026.
  * workflows: <sessao>/subagents/workflows/wf_<runId>/journal.jsonl + agent-*.jsonl
    e o roteiro <sessao>/workflows/scripts/*<runId>.js.
    Formato ainda NÃO conferido em disco (nenhum workflow tinha rodado na máquina).
"""

import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
import sys
import threading
import time
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOME = Path.home()
PASTA_PROJETOS = HOME / ".claude" / "projects"
PASTA_SESSOES = HOME / ".claude" / "sessions"
PASTA_PAINEL = Path(__file__).resolve().parent
APP_ID = "teklabs-painel-agentes"
VERSAO = "1.0.0"


def _ler_config():
    """config.json ao lado do painel (gravado pelo instalador): workspace e porta."""
    try:
        dados = json.loads((PASTA_PAINEL / "config.json").read_text(encoding="utf-8", errors="replace"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


CONFIG = _ler_config()
# Ordem: variável de ambiente > config.json (gravado pelo instalador) > pasta do usuário.
WORKSPACE = Path(os.environ.get("MONITOR_WORKSPACE") or CONFIG.get("workspace") or HOME)

JANELA_SEGUNDOS = 7 * 24 * 3600
ATIVO_SEGUNDOS = 90
PARADO_SEGUNDOS = 30 * 60
PORTA_INICIAL = 8765
# Portas comuns de frameworks, bancos e serviços de desenvolvimento (inclui 5433/5434 do túnel Postgres).
PORTAS_EVITADAS = {3000, 3001, 4200, 5000, 5001, 5173, 5432, 5433, 5434, 6379, 8000, 8001,
                   8080, 8081, 8443, 8888, 9000, 9090, 27017}

CRITERIO_CWD_AGENTES = "pasta de trabalho gravada nos agentes"
CRITERIO_CWD_GERENTE = "pasta de trabalho da conversa do gerente"
CRITERIO_PASTA_SESSAO = "nome da pasta da sessão"
CRITERIO_ROTEIRO = "caminho do projeto citado no roteiro"

TERMINAIS = {"concluído", "falhou", "interrompido", "repetido"}
STATUS_TERMINAL = {
    "completed": "concluído",
    "failed": "falhou",
    "killed": "interrompido",
    "stopped": "interrompido",
    "cancelled": "interrompido",
}


# ---------------------------------------------------------------- leitura de arquivo

def ler_texto(caminho):
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def ler_json(caminho):
    texto = ler_texto(caminho)
    if texto is None:
        return None
    try:
        return json.loads(texto)
    except ValueError:
        return None


def ler_jsonl(caminho):
    """Uma lista de objetos; linhas incompletas ou inválidas são ignoradas."""
    texto = ler_texto(caminho)
    eventos = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            obj = json.loads(linha)
        except ValueError:
            continue
        if isinstance(obj, dict):
            eventos.append(obj)
    return eventos


def estatistica(caminho):
    try:
        return caminho.stat()
    except OSError:
        return None


def tempos_do_arquivo(st):
    """(inicio, ultima_escrita) em segundos epoch.

    No Windows st_ctime é a data de criação. Em outros sistemas st_ctime é a
    troca de metadados, então usa st_birthtime quando existe.
    """
    fim = st.st_mtime
    if sys.platform == "win32":
        inicio = st.st_ctime
    else:
        inicio = getattr(st, "st_birthtime", None)
        if inicio is None:
            inicio = min(st.st_ctime, st.st_mtime)
    return min(inicio, fim), fim


_cache = {}
_cache_lock = threading.Lock()


def em_cache(caminho, funcao):
    """Reaproveita o resultado enquanto tamanho e data do arquivo não mudarem."""
    st = estatistica(caminho)
    if st is None:
        return None
    chave = (st.st_size, st.st_mtime_ns)
    with _cache_lock:
        item = _cache.get((funcao.__name__, str(caminho)))
    if item and item[0] == chave:
        return item[1]
    valor = funcao(caminho)
    with _cache_lock:
        _cache[(funcao.__name__, str(caminho))] = (chave, valor)
    return valor


RE_CWD = re.compile(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"')
RE_PRINCIPAL = re.compile(r'"isSidechain"\s*:\s*false')


def cwd_do_agente(caminho):
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            for i, linha in enumerate(f):
                m = RE_CWD.search(linha)
                if m:
                    try:
                        return json.loads('"' + m.group(1) + '"')
                    except ValueError:
                        pass
                if i > 200:
                    break
    except OSError:
        pass
    return None


_cwd_fixo = {}


def cwd_em_cache(caminho):
    chave = str(caminho)
    if chave not in _cwd_fixo:
        cwd = cwd_do_agente(caminho)
        if cwd is None:
            return None
        _cwd_fixo[chave] = cwd
    return _cwd_fixo[chave]


# ---------------------------------------------------------------- consumo de tokens

# Peso relativo ao token de entrada, igual em todos os modelos Claude:
# cache criado 1,25x, cache lido 0,1x, saída 5x.
PESOS = {"entrada": 1.0, "cache_criado": 1.25, "cache_lido": 0.1, "saida": 5.0}


class Consumo:
    """Soma o usage das chamadas de um arquivo de conversa, lendo só o que foi acrescentado.

    Cada chamada aparece em várias linhas com o mesmo message.id enquanto é gerada;
    vale o maior valor de cada campo (o último).
    """

    def __init__(self):
        self.posicao = 0
        self.chamadas = {}

    def atualizar(self, caminho):
        st = estatistica(caminho)
        if st is None:
            return
        if st.st_size < self.posicao:
            self.__init__()
        if st.st_size == self.posicao:
            return
        try:
            with open(caminho, "rb") as f:
                f.seek(self.posicao)
                bruto = f.read(st.st_size - self.posicao)
        except OSError:
            return
        fim = bruto.rfind(b"\n")
        if fim < 0:
            return
        self.posicao += fim + 1
        for linha in bruto[:fim].decode("utf-8", errors="replace").splitlines():
            self.linha(linha)

    def linha(self, linha):
        if '"usage"' not in linha or '"assistant"' not in linha:
            return
        obj = _carregar(linha)
        msg = (obj or {}).get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            return
        u = msg["usage"]
        valores = (
            int(u.get("input_tokens") or 0),
            int(u.get("cache_creation_input_tokens") or 0),
            int(u.get("cache_read_input_tokens") or 0),
            int(u.get("output_tokens") or 0),
        )
        chave = msg.get("id") or (obj.get("uuid") if obj else None)
        anterior = self.chamadas.get(chave)
        if anterior:
            valores = tuple(max(a, b) for a, b in zip(anterior[0], valores))
        self.chamadas[chave] = (valores, msg.get("model") or (anterior[1] if anterior else None))

    def resumo(self):
        soma = [0, 0, 0, 0]
        modelos = {}
        for valores, modelo in self.chamadas.values():
            for i, v in enumerate(valores):
                soma[i] += v
            if modelo:
                modelos[modelo] = modelos.get(modelo, 0) + 1
        entrada, criado, lido, saida = soma
        return {
            "chamadas": len(self.chamadas),
            "entrada": entrada,
            "cache_criado": criado,
            "cache_lido": lido,
            "saida": saida,
            "equivalente": round(entrada * PESOS["entrada"] + criado * PESOS["cache_criado"]
                                 + lido * PESOS["cache_lido"] + saida * PESOS["saida"]),
            "modelos": modelos,
        }


def somar_consumo(lista):
    total = {"chamadas": 0, "entrada": 0, "cache_criado": 0, "cache_lido": 0,
             "saida": 0, "equivalente": 0, "modelos": {}}
    for c in lista:
        if not c:
            continue
        for k in ("chamadas", "entrada", "cache_criado", "cache_lido", "saida", "equivalente"):
            total[k] += c.get(k, 0)
        for m, n in (c.get("modelos") or {}).items():
            total["modelos"][m] = total["modelos"].get(m, 0) + n
    return total


_consumos = {}


def consumo_do_arquivo(caminho):
    contador = _consumos.setdefault(str(caminho), Consumo())
    contador.atualizar(caminho)
    return contador.resumo()


# ---------------------------------------------------------------- conversa do gerente

RE_NOTIFICACAO = re.compile(r"<task-id>([^<]+)</task-id>.*?<status>([^<]+)</status>", re.S)


class LeitorSessao:
    """Lê a conversa do gerente aos poucos (só o que foi acrescentado desde a última vez)."""

    def __init__(self):
        self.posicao = 0
        self.status = {}
        self.resultados = {}
        self.titulo = None
        self.cwd = None

    def atualizar(self, caminho):
        st = estatistica(caminho)
        if st is None:
            return
        if st.st_size < self.posicao:
            self.__init__()
        if st.st_size == self.posicao:
            return
        try:
            with open(caminho, "rb") as f:
                f.seek(self.posicao)
                bruto = f.read(st.st_size - self.posicao)
        except OSError:
            return
        fim = bruto.rfind(b"\n")
        if fim < 0:
            return
        self.posicao += fim + 1
        for linha in bruto[:fim].decode("utf-8", errors="replace").splitlines():
            self._linha(linha)

    def _status(self, tarefa, situacao, momento):
        # Status não final nunca apaga um final: agente retomado é detectado
        # pela escrita no arquivo dele depois do horário do aviso de fim.
        anterior = self.status.get(tarefa)
        if anterior and anterior[0] in STATUS_TERMINAL and situacao not in STATUS_TERMINAL:
            return
        self.status[tarefa] = (situacao, momento)

    def _linha(self, linha):
        if '"ai-title"' in linha:
            obj = _carregar(linha)
            if obj and obj.get("aiTitle"):
                self.titulo = obj["aiTitle"]
            return
        m = RE_CWD.search(linha)
        if m and RE_PRINCIPAL.search(linha):
            try:
                self.cwd = json.loads('"' + m.group(1) + '"')
            except ValueError:
                pass
        if '"task_status"' in linha:
            obj = _carregar(linha)
            anexo = (obj or {}).get("attachment") or {}
            if anexo.get("type") == "task_status" and anexo.get("taskId"):
                self._status(anexo["taskId"], anexo.get("status"), _momento(linha))
        if "<task-notification>" in linha:
            for tarefa, situacao in RE_NOTIFICACAO.findall(linha):
                self._status(tarefa.strip(), situacao.strip(), _momento(linha))
        if '"tool_result"' in linha:
            obj = _carregar(linha)
            conteudo = ((obj or {}).get("message") or {}).get("content")
            if isinstance(conteudo, list):
                for item in conteudo:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        self.resultados[item.get("tool_use_id")] = (
                            _texto_inicial(item.get("content")),
                            bool(item.get("is_error")),
                            _momento(linha),
                        )


RE_MOMENTO = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')


def _momento(linha):
    """Horário gravado na linha (ISO 8601, UTC) em segundos epoch, ou None."""
    m = RE_MOMENTO.search(linha)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _carregar(linha):
    try:
        obj = json.loads(linha)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _texto_inicial(conteudo):
    if isinstance(conteudo, str):
        return conteudo[:80]
    if isinstance(conteudo, list):
        for parte in conteudo:
            if isinstance(parte, dict) and isinstance(parte.get("text"), str):
                return parte["text"][:80]
    return ""


_leitores = {}


def leitor_da_sessao(caminho):
    leitor = _leitores.setdefault(str(caminho), LeitorSessao())
    leitor.atualizar(caminho)
    return leitor


# ---------------------------------------------------------------- projeto

def listar_projetos():
    try:
        return sorted(
            (p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=str.casefold,
        )
    except OSError:
        return []


def normalizar(texto):
    # Mesma troca que o Claude Code faz ao nomear a pasta da sessão
    # (: \ / _ . espaço e qualquer outro caractere fora de letra e número viram hífen).
    return re.sub(r"[^A-Za-z0-9]", "-", texto).casefold()


def projeto_do_caminho(caminho, projetos):
    try:
        partes = [p.casefold() for p in Path(caminho).parts]
    except (TypeError, ValueError):
        return None
    base = [p.casefold() for p in WORKSPACE.parts]
    if len(partes) > len(base) and partes[: len(base)] == base:
        alvo = partes[len(base)]
        for nome in projetos:
            if nome.casefold() == alvo:
                return nome
    return None


def projeto_da_pasta_sessao(nome_pasta, projetos):
    alvo = normalizar(nome_pasta)
    melhor = None
    for nome in projetos:
        n = normalizar(str(WORKSPACE / nome))
        if alvo == n or alvo.startswith(n + "-"):
            if melhor is None or len(n) > len(melhor[0]):
                melhor = (n, nome)
    return melhor[1] if melhor else None


def projeto_do_roteiro(texto, projetos):
    """Procura no roteiro caminhos absolutos que passam pela workspace."""
    if not texto:
        return None
    corpo = texto.replace("\\\\", "\\").replace("/", "\\").casefold()
    raiz = str(WORKSPACE).replace("/", "\\").casefold().rstrip("\\") + "\\"
    contagem = {}
    inicio = corpo.find(raiz)
    while inicio >= 0:
        resto = corpo[inicio + len(raiz):]
        melhor = None
        for nome in projetos:
            n = nome.casefold()
            if resto.startswith(n) and (len(resto) == len(n) or resto[len(n)] in "\\\"'`\n\r\t ,;)"):
                if melhor is None or len(n) > len(melhor.casefold()):
                    melhor = nome
        if melhor:
            contagem[melhor] = contagem.get(melhor, 0) + 1
        inicio = corpo.find(raiz, inicio + 1)
    if not contagem:
        return None
    return max(contagem.items(), key=lambda kv: kv[1])[0]


# ---------------------------------------------------------------- time de agentes avulsos

def situacao_do_time(agentes):
    situacoes = {a["situacao"] for a in agentes}
    if "trabalhando" in situacoes:
        return "trabalhando"
    if situacoes & {"em andamento", "na fila"}:
        return "em andamento"
    if "parado" in situacoes:
        return "parado"
    return "encerrado"


def sessoes_abertas():
    """Registro do Claude Code em ~/.claude/sessions/<pid>.json: sessionId -> dados."""
    abertas = {}
    if not PASTA_SESSOES.is_dir():
        return abertas
    for p in PASTA_SESSOES.glob("*.json"):
        dados = em_cache(p, ler_json)
        if not isinstance(dados, dict) or not dados.get("sessionId"):
            continue
        atual = abertas.get(dados["sessionId"])
        if atual is None or (dados.get("updatedAt") or 0) > (atual.get("updatedAt") or 0):
            abertas[dados["sessionId"]] = dados
    return abertas


STATUS_SESSAO_ATIVA = {"busy", "waiting"}


def sessao_ativa(registro):
    return bool(registro) and registro.get("status") in STATUS_SESSAO_ATIVA


def situacao_com_gerente(situacao, gerente):
    """O gerente pesa na situação do time: trabalhando ou esperando você nunca é 'encerrado'."""
    if gerente["situacao"] == "aguardando":
        return "aguardando"
    if gerente["situacao"] == "trabalhando":
        return "trabalhando"
    if gerente["situacao"] == "ocupado" and situacao in ("encerrado", "parado"):
        return "em andamento"
    return situacao


def situacao_do_gerente(registro, st_conversa, agora):
    ultima = st_conversa.st_mtime if st_conversa else None
    base = {
        "ultima_escrita": ultima,
        "nome_sessao": (registro or {}).get("name"),
        "status_desde": ((registro or {}).get("statusUpdatedAt") or 0) / 1000 or None,
    }
    if not registro:
        return {**base, "situacao": "fechado"}
    status = registro.get("status")
    if status == "busy":
        escrevendo = ultima is not None and agora - ultima <= ATIVO_SEGUNDOS
        return {**base, "situacao": "trabalhando" if escrevendo else "ocupado"}
    if status == "idle":
        return {**base, "situacao": "ocioso"}
    if status == "waiting":
        # Conferido em 02/10/2026: waitingFor = "permission prompt" quando pede aprovação.
        motivo = str(registro.get("waitingFor") or "")
        return {**base, "situacao": "aguardando",
                "motivo": "pedido de permissão" if "permission" in motivo else motivo}
    return {**base, "situacao": status or "fechado"}


def times_de_agentes(pasta, sessao, sub, agora, projetos, registro=None):
    arquivos = []
    for p in sub.glob("agent-*.jsonl"):
        st = estatistica(p)
        if st is not None:
            arquivos.append((p, st))
    ocupada = sessao_ativa(registro)
    conversa = pasta / (sessao.name + ".jsonl")
    st_conversa = estatistica(conversa)
    if not arquivos and not (ocupada and st_conversa):
        # Sem agentes e sem conversa nesta pasta: não há o que mostrar daqui.
        return []
    recente = ocupada or any(agora - st.st_mtime <= JANELA_SEGUNDOS for _, st in arquivos)
    leitor = leitor_da_sessao(conversa) if recente else None
    gerente = situacao_do_gerente(registro, st_conversa, agora)

    grupos = {}
    tem_workflow = (sub / "workflows").is_dir() and any(
        p.is_dir() and p.name.startswith("wf_") for p in (sub / "workflows").iterdir())
    if not arquivos and tem_workflow:
        return []  # o gerente aparece no cartão do workflow
    if not arquivos:
        # Sessão ocupada que ainda não lançou agentes: o time é só o gerente.
        projeto, criterio = None, None
        if leitor and leitor.cwd:
            projeto = projeto_do_caminho(leitor.cwd, projetos)
            criterio = CRITERIO_CWD_GERENTE if projeto else None
        if projeto is None:
            projeto = projeto_da_pasta_sessao(pasta.name, projetos)
            criterio = CRITERIO_PASTA_SESSAO if projeto else None
        grupos[projeto] = []
        criterios_vazios = {projeto: [criterio] if criterio else []}
    else:
        criterios_vazios = {}
    for p, st in arquivos:
        projeto, criterio = None, None
        cwd = cwd_em_cache(p)
        if cwd:
            projeto = projeto_do_caminho(cwd, projetos)
            criterio = CRITERIO_CWD_AGENTES
        if projeto is None and leitor and leitor.cwd:
            projeto = projeto_do_caminho(leitor.cwd, projetos)
            criterio = CRITERIO_CWD_GERENTE
        if projeto is None:
            projeto = projeto_da_pasta_sessao(pasta.name, projetos)
            criterio = CRITERIO_PASTA_SESSAO if projeto else None
        grupos.setdefault(projeto, []).append((p, st, criterio))

    times = []
    for projeto, itens in grupos.items():
        escritas = [st.st_mtime for _, st, _ in itens]
        if ocupada and st_conversa:
            escritas.append(st_conversa.st_mtime)
        if not escritas:
            continue
        ultima = max(escritas)
        if agora - ultima > JANELA_SEGUNDOS or leitor is None:
            times.append({"antigo": True, "projeto": projeto})
            continue

        agentes = []
        for p, st, _ in itens:
            aid = p.stem[len("agent-"):]
            meta = em_cache(p.with_name(f"agent-{aid}.meta.json"), ler_json)
            meta = meta if isinstance(meta, dict) else {}
            inicio, fim = tempos_do_arquivo(st)

            terminal, quando_terminou = None, None
            sinal, quando = leitor.status.get(aid, (None, None))
            terminal = STATUS_TERMINAL.get(sinal)
            if terminal:
                quando_terminou = quando
            else:
                resultado = leitor.resultados.get(meta.get("toolUseId"))
                if resultado and not resultado[0].startswith("Async agent launched"):
                    terminal = "falhou" if resultado[1] else "concluído"
                    quando_terminou = resultado[2]

            # Escrita depois do aviso de fim = agente retomado; antes disso, vale o aviso.
            retomado = terminal and quando_terminou is not None and fim > quando_terminou + 5
            escrevendo = agora - fim <= ATIVO_SEGUNDOS
            if terminal and not retomado:
                situacao = terminal
            elif escrevendo:
                situacao = "trabalhando"
            elif agora - fim > PARADO_SEGUNDOS:
                situacao = "parado"
            else:
                situacao = "em andamento"

            nome = meta.get("description") or f"agente {aid[:8]}"
            agentes.append({
                "nome": nome,
                "fase": codigo_de_fase(nome)[0],
                "situacao": situacao,
                "segundo_plano": meta.get("requestShape") == "background",
                "inicio": inicio,
                "ultima_escrita": fim,
                "duracao": (fim if situacao in TERMINAIS else agora) - inicio,
                "bytes": st.st_size,
                "consumo": consumo_do_arquivo(p),
            })
        agentes.sort(key=lambda a: a["inicio"])

        concluidos = sum(1 for a in agentes if a["situacao"] in TERMINAIS)
        criterios = sorted({c for _, _, c in itens if c}) or criterios_vazios.get(projeto, [])
        if agentes:
            inicio_time = min(a["inicio"] for a in agentes)
        else:
            inicio_time = tempos_do_arquivo(st_conversa)[0] if st_conversa else agora
        situacao = situacao_com_gerente(situacao_do_time(agentes), gerente)
        times.append({
            "id": f"agentes:{sessao.name}:{projeto or ''}",
            "tipo": "agentes",
            "nome": leitor.titulo or f"Conversa {sessao.name[:8]}",
            "sessao": sessao.name,
            "projeto": projeto,
            "criterio_projeto": criterios,
            "criterio_confirmado": True,
            "inicio": inicio_time,
            "ultima_escrita": ultima,
            "situacao": situacao,
            "gerente": gerente,
            "consumo_agentes": somar_consumo([a["consumo"] for a in agentes]),
            "consumo_gerente": consumo_do_arquivo(conversa) if st_conversa else None,
            "medido": {
                "lancados": len(agentes),
                "iniciados": len(agentes),
                "concluidos": concluidos,
                "trabalhando": sum(1 for a in agentes if a["situacao"] == "trabalhando"),
                "repetidos": 0,
                "falharam": sum(1 for a in agentes if a["situacao"] in ("falhou", "interrompido")),
            },
            "fases": [],
            "estimativa": {
                "base": False,
                "motivo": "Time sem fases declaradas: não há base para estimar o total de agentes.",
            },
            "agentes": agentes,
        })
    return times


# ---------------------------------------------------------------- workflow

def extrair_bloco(texto, abre_em, abre="{", fecha="}"):
    if abre_em < 0:
        return ""
    nivel, aspas, i = 0, None, abre_em
    while i < len(texto):
        c = texto[i]
        if aspas:
            if c == "\\":
                i += 2
                continue
            if c == aspas:
                aspas = None
        elif c in "'\"`":
            aspas = c
        elif c == abre:
            nivel += 1
        elif c == fecha:
            nivel -= 1
            if nivel == 0:
                return texto[abre_em: i + 1]
        i += 1
    return texto[abre_em:]


RE_NOME = re.compile(r"\bname\s*:\s*(['\"`])((?:(?!\1).)*)\1", re.S)
RE_TITULO = re.compile(r"\btitle\s*:\s*(['\"`])((?:(?!\1).)*)\1", re.S)


def ler_roteiro(caminho):
    texto = ler_texto(caminho) or ""
    nome, fases = None, []
    i = texto.find("export const meta")
    if i >= 0:
        bloco = extrair_bloco(texto, texto.find("{", i))
        m = RE_NOME.search(bloco)
        if m:
            nome = m.group(2)
        k = bloco.find("phases")
        if k >= 0:
            lista = extrair_bloco(bloco, bloco.find("[", k), "[", "]")
            fases = [m.group(2) for m in RE_TITULO.finditer(lista)]
    return {"texto": texto, "nome": nome, "fases": fases}


def achar_roteiro(sessao, run):
    ids = {run}
    if run.startswith("wf_"):
        ids.add(run[3:])
    # Conferido em 02/10/2026: o roteiro fica em <pasta do projeto>\<sessao>\workflows\scripts,
    # que pode ser outra pasta de .claude\projects (a do cwd), não a da execução.
    candidatos = []
    for rid in ids:
        candidatos.extend(PASTA_PROJETOS.glob(f"*/{sessao.name}/workflows/scripts/*{rid}.js"))
        candidatos.extend(PASTA_PROJETOS.glob(f"*/{sessao.name}/subagents/workflows/scripts/*{rid}.js"))
    candidatos = [c for c in candidatos if estatistica(c)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.stat().st_mtime)


def _chave(valor):
    return valor if isinstance(valor, str) else json.dumps(valor, sort_keys=True)


def time_de_workflow(pasta, sessao, wf, agora, projetos, registro=None):
    arquivos = []
    for p in wf.iterdir():
        st = estatistica(p) if p.is_file() else None
        if st is not None:
            arquivos.append((p, st))
    roteiro_arq = achar_roteiro(sessao, wf.name)
    roteiro = em_cache(roteiro_arq, ler_roteiro) if roteiro_arq else None
    if not arquivos and not roteiro_arq:
        return None
    ultima = max([st.st_mtime for _, st in arquivos] or [0])

    projeto, criterio = None, None
    if roteiro:
        projeto = projeto_do_roteiro(roteiro["texto"], projetos)
        criterio = CRITERIO_ROTEIRO if projeto else None
    if projeto is None:
        for p, _ in arquivos:
            if p.name.startswith("agent-") and p.suffix == ".jsonl":
                cwd = cwd_em_cache(p)
                projeto = projeto_do_caminho(cwd, projetos) if cwd else None
                if projeto:
                    criterio = CRITERIO_CWD_AGENTES
                    break
    if projeto is None:
        projeto = projeto_da_pasta_sessao(pasta.name, projetos)
        criterio = CRITERIO_PASTA_SESSAO if projeto else None

    if agora - ultima > JANELA_SEGUNDOS:
        return {"antigo": True, "projeto": projeto}

    eventos = em_cache(wf / "journal.jsonl", ler_jsonl) or []
    ordem, dados = [], {}
    ultimo_por_chave = {}
    for ev in eventos:
        aid = ev.get("agentId")
        if not aid and ev.get("type") == "result" and ev.get("key") is not None:
            # result sem agentId: atribui ao último agente iniciado com a mesma key
            aid = ultimo_por_chave.get(_chave(ev["key"]))
        if not aid:
            continue  # o "launched" real é um só por workflow, sem agentId
        if ev.get("key") is not None and ev.get("type") != "result":
            ultimo_por_chave[_chave(ev["key"])] = aid
        if aid not in dados:
            ordem.append(aid)
            dados[aid] = {"label": None, "phase": None, "key": None,
                          "launched": False, "started": False, "result": False}
        a = dados[aid]
        for campo in ("label", "phase", "key"):
            if a[campo] is None and ev.get(campo) is not None:
                a[campo] = ev.get(campo)
        if ev.get("type") in ("launched", "started", "result"):
            a[ev["type"]] = True

    stats_agente = {p.stem[len("agent-"):]: st for p, st in arquivos
                    if p.name.startswith("agent-") and p.suffix == ".jsonl"}
    for aid in stats_agente:
        if aid not in dados:
            ordem.append(aid)
            dados[aid] = {"label": None, "phase": None, "key": None,
                          "launched": True, "started": True, "result": False}
    for aid in ordem:
        a = dados[aid]
        if a["label"] is None or a["phase"] is None:
            meta = em_cache(wf / f"agent-{aid}.meta.json", ler_json)
            meta = meta if isinstance(meta, dict) else {}
            if a["label"] is None:
                a["label"] = meta.get("description")
            if a["phase"] is None:
                a["phase"] = meta.get("workflowPhase")

    chaves_com_result = {_chave(a["key"]) for a in dados.values() if a["result"] and a["key"] is not None}

    agentes = []
    for aid in ordem:
        a = dados[aid]
        st = stats_agente.get(aid)
        inicio, fim = tempos_do_arquivo(st) if st else (None, None)
        escrevendo = fim is not None and agora - fim <= ATIVO_SEGUNDOS
        if a["result"]:
            situacao = "concluído"
        elif a["key"] is not None and _chave(a["key"]) in chaves_com_result:
            situacao = "repetido"
        elif escrevendo:
            situacao = "trabalhando"
        elif a["started"] or st:
            ref = fim if fim is not None else ultima
            situacao = "parado" if agora - ref > PARADO_SEGUNDOS else "em andamento"
        else:
            situacao = "na fila"
        duracao = None
        if inicio is not None:
            duracao = (fim if situacao in TERMINAIS else agora) - inicio
        fase = a["phase"]
        agentes.append({
            "nome": a["label"] or f"agente {aid[:8]}",
            "fase": fase if isinstance(fase, str) or fase is None else str(fase),
            "situacao": situacao,
            "segundo_plano": None,
            "inicio": inicio,
            "ultima_escrita": fim,
            "duracao": duracao,
            "bytes": st.st_size if st else 0,
            "consumo": consumo_do_arquivo(wf / f"agent-{aid}.jsonl") if st else None,
            "iniciado": bool(a["started"] or st),
        })

    # fases: as do roteiro, na ordem; fases citadas no journal e ausentes no roteiro vão ao fim
    titulos = list((roteiro or {}).get("fases") or [])
    for a in agentes:
        if a["fase"] and a["fase"] not in titulos:
            titulos.append(a["fase"])
    por_fase = {t: 0 for t in titulos}
    abertos_por_fase = {t: 0 for t in titulos}
    for a in agentes:
        if a["fase"] in por_fase:
            por_fase[a["fase"]] += 1
            if a["situacao"] not in TERMINAIS:
                abertos_por_fase[a["fase"]] += 1
    iniciadas = [i for i, t in enumerate(titulos) if por_fase[t] > 0]
    atual = max(iniciadas) if iniciadas else -1
    todos_encerrados = bool(agentes) and all(a["situacao"] in TERMINAIS for a in agentes)
    terminou = bool(todos_encerrados and titulos and atual == len(titulos) - 1)

    # Uma fase só é "feita" quando todos os agentes dela encerraram; fase que o
    # roteiro pulou (zero agentes antes da atual) aparece como feita, mas não entra na média.
    fases = []
    for i, t in enumerate(titulos):
        if i > atual:
            estado = "futura"
        elif abertos_por_fase[t] > 0 or (i == atual and not terminou):
            estado = "atual"
        else:
            estado = "feita"
        fases.append({"titulo": t, "estado": estado, "agentes": por_fase[t],
                      "no_roteiro": t in ((roteiro or {}).get("fases") or [])})

    encerrados = sum(1 for a in agentes if a["situacao"] in TERMINAIS)
    lancados = len(agentes)
    feitas = [f for f in fases if f["estado"] == "feita" and f["agentes"] > 0]
    restantes = sum(1 for f in fases if f["estado"] == "futura")
    inicio_time = min([a["inicio"] for a in agentes if a["inicio"] is not None] or
                      [min((tempos_do_arquivo(st)[0] for _, st in arquivos), default=agora)])
    if not feitas:
        estimativa = {"base": False, "motivo": "Sem base para estimar ainda: nenhuma fase terminou."}
    else:
        media = sum(f["agentes"] for f in feitas) / len(feitas)
        total = max(lancados, int(lancados + media * restantes + 0.5))
        porcentagem = 100.0 if terminou else min(100.0, 100.0 * encerrados / total) if total else 0.0
        restante = None
        if terminou:
            restante = 0
        elif encerrados > 0 and total > encerrados:
            restante = (agora - inicio_time) / encerrados * (total - encerrados)
        estimativa = {
            "base": True,
            "media_por_fase": round(media, 1),
            "fases_restantes": restantes,
            "total": total,
            "porcentagem": round(porcentagem),
            "restante_segundos": restante,
        }

    conversas = [c for c in PASTA_PROJETOS.glob(f"*/{sessao.name}.jsonl") if estatistica(c)]
    st_conversa = estatistica(max(conversas, key=lambda c: c.stat().st_mtime)) if conversas else None
    gerente = situacao_do_gerente(registro, st_conversa, agora)
    situacao = situacao_com_gerente(situacao_do_time(agentes) if agentes else "em andamento", gerente)

    return {
        "id": f"workflow:{sessao.name}:{wf.name}",
        "tipo": "workflow",
        "nome": (roteiro or {}).get("nome") or wf.name,
        "sessao": sessao.name,
        "projeto": projeto,
        "criterio_projeto": [criterio] if criterio else [],
        "criterio_confirmado": True,
        "inicio": inicio_time,
        "ultima_escrita": ultima,
        "situacao": situacao,
        "gerente": gerente,
        "consumo_agentes": somar_consumo([a["consumo"] for a in agentes]),
        "consumo_gerente": (consumo_do_arquivo(max(conversas, key=lambda c: c.stat().st_mtime))
                            if conversas else None),
        "medido": {
            "lancados": lancados,
            "iniciados": sum(1 for a in agentes if a["iniciado"]),
            "concluidos": encerrados,
            "trabalhando": sum(1 for a in agentes if a["situacao"] == "trabalhando"),
            "repetidos": sum(1 for a in agentes if a["situacao"] == "repetido"),
            "falharam": 0,
        },
        "fases": fases,
        "estimativa": estimativa,
        "roteiro_encontrado": roteiro_arq is not None,
        "result_visto": any(ev.get("type") == "result" for ev in eventos),
        "agentes": agentes,
    }


# ---------------------------------------------------------------- planos do CTO

RE_CODIGO_FASE = re.compile(r"^\s*(QA\s+)?(F\d+(?:\.\d+)*)\b", re.I)


def codigo_de_fase(nome):
    """'F1.2 Especialista x' -> ('F1.2', False); 'QA F1' -> ('F1', True); sem prefixo -> (None, False)."""
    m = RE_CODIGO_FASE.match(nome or "")
    if not m:
        return None, False
    return m.group(2).upper(), bool(m.group(1))


def _instante(texto, reserva):
    try:
        return datetime.fromisoformat(str(texto).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return reserva


def montar_planos(times, projetos, agora, avisos):
    """Planos gravados pelo CTO em monitor/planos/*.json, com os agentes medidos de cada fase."""
    pasta = PASTA_PAINEL / "planos"
    if not pasta.is_dir():
        return []
    por_nome = {p.casefold(): p for p in projetos}
    planos = []
    for arq in sorted(pasta.glob("*.json")):
        st = estatistica(arq)
        dados = em_cache(arq, ler_json)
        if st is None:
            continue
        if not isinstance(dados, dict) or not isinstance(dados.get("fases"), list):
            avisos.append(f"plano {arq.name}: arquivo em formato inesperado (falta a lista 'fases')")
            continue
        criado = _instante(dados.get("criado_em"), tempos_do_arquivo(st)[0])
        atualizado = max(_instante(dados.get("atualizado_em"), 0), st.st_mtime)
        situacao = str(dados.get("situacao") or "em andamento")
        if situacao != "em andamento" and agora - atualizado > JANELA_SEGUNDOS:
            continue
        projeto = por_nome.get(str(dados.get("projeto") or "").casefold())
        if projeto is None:
            avisos.append(f"plano {arq.name}: projeto '{dados.get('projeto')}' não existe na workspace")
        planos.append({"arquivo": arq.name, "dados": dados, "projeto": projeto,
                       "criado_em": criado, "atualizado_em": atualizado, "situacao": situacao})

    # Cada agente com prefixo de fase vai para o plano mais recente do projeto criado antes dele.
    agentes_por_plano = {id(p): [] for p in planos}
    for t in times:
        for a in t["agentes"]:
            codigo, eh_qa = codigo_de_fase(a["nome"])
            if not codigo or a.get("inicio") is None:
                continue
            candidatos = [p for p in planos if p["projeto"] == t["projeto"]
                          and p["criado_em"] - 120 <= a["inicio"]]
            if candidatos:
                dono = max(candidatos, key=lambda p: p["criado_em"])
                agentes_por_plano[id(dono)].append((codigo, eh_qa, a))

    saida = []
    for p in planos:
        ligados = agentes_por_plano[id(p)]
        ids_fases = [str(f.get("id") or "").upper() for f in p["dados"]["fases"]
                     if isinstance(f, dict) and f.get("id")]

        def fase_dona(codigo):
            # Cada agente cai numa fase só: a de id mais longo que é ele mesmo ou ancestral dele.
            donas = [i for i in ids_fases if codigo == i or codigo.startswith(i + ".")]
            return max(donas, key=len) if donas else None

        dono_de = [fase_dona(c) for c, _, _ in ligados]
        fases = []
        for f in p["dados"]["fases"]:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("id") or "").upper()
            subfases = [s for s in (f.get("subfases") or []) if isinstance(s, dict)]
            da_fase = [item for item, dono in zip(ligados, dono_de) if fid and dono == fid]
            especialistas = [a for c, q, a in da_fase if not q]
            fases.append({
                "id": fid,
                "titulo": str(f.get("titulo") or fid),
                "situacao": str(f.get("situacao") or "pendente"),
                "subfases": [{
                    "id": str(s.get("id") or "").upper(),
                    "titulo": str(s.get("titulo") or s.get("id") or ""),
                    "situacao": str(s.get("situacao") or "pendente"),
                    "agentes": sum(1 for c, q, a in da_fase
                                   if not q and c == str(s.get("id") or "").upper()),
                } for s in subfases],
                "agentes": len(especialistas),
                "trabalhando": sum(1 for a in especialistas if a["situacao"] == "trabalhando"),
                "encerrados": sum(1 for a in especialistas if a["situacao"] in TERMINAIS),
                "qa": [{"nome": a["nome"], "situacao": a["situacao"]} for c, q, a in da_fase if q],
                "consumo_especialistas": somar_consumo([a.get("consumo") for a in especialistas]),
                "consumo_qa": somar_consumo([a.get("consumo") for c, q, a in da_fase if q]),
            })

        total_fases = len(fases)
        aprovadas = [f for f in fases if f["situacao"] == "aprovada"]
        pendentes = sum(1 for f in fases if f["situacao"] == "pendente")
        lancados = sum(f["agentes"] for f in fases)
        com_agentes = [f for f in aprovadas if f["agentes"] > 0]
        if not aprovadas:
            estimativa = {"base": False, "motivo": "Sem base para estimar ainda: nenhuma fase foi aprovada pelo QA."}
        else:
            decorrido = agora - p["criado_em"]
            faltam = total_fases - len(aprovadas)
            estimativa = {
                "base": True,
                "restante_segundos": decorrido / len(aprovadas) * faltam if faltam else 0,
                "total_agentes": (int(lancados + sum(f["agentes"] for f in com_agentes) / len(com_agentes)
                                      * pendentes + 0.5) if com_agentes else None),
            }
        saida.append({
            "arquivo": p["arquivo"],
            "demanda": str(p["dados"].get("demanda") or p["arquivo"]),
            "projeto": p["projeto"],
            "situacao": p["situacao"],
            "criado_em": p["criado_em"],
            "atualizado_em": p["atualizado_em"],
            "fases": fases,
            "fases_aprovadas": len(aprovadas),
            "total_fases": total_fases,
            "agentes_ligados": len(ligados),
            "estimativa": estimativa,
        })
    saida.sort(key=lambda p: (p["situacao"] != "em andamento", -p["atualizado_em"]))
    return saida


# ---------------------------------------------------------------- Codex

# Conferido em 07/10/2026 (Codex 0.155, VS Code e Desktop): cada conversa é um
# sessions/AAAA/MM/DD/rollout-*.jsonl. A 1ª linha (session_meta) traz id, cwd, source e,
# nos subagentes, source {"subagent": ...} e parent_thread_id. Turnos: event_msg
# task_started / task_complete. Tokens: o último event_msg token_count traz o total acumulado.
# Só os arquivos .jsonl são lidos; os bancos sqlite do Codex não são abertos.
PASTA_CODEX = Path(os.environ.get("CODEX_HOME") or (HOME / ".codex"))


class LeitorCodex:
    def __init__(self):
        self.posicao = 0
        self.meta = {}
        self.titulo = None
        self.abertos = set()
        self.ultimo_inicio = None
        self.ultimo_fim = None
        self.tokens = None

    def atualizar(self, caminho):
        st = estatistica(caminho)
        if st is None:
            return
        if st.st_size < self.posicao:
            self.__init__()
        if st.st_size == self.posicao:
            return
        try:
            with open(caminho, "rb") as f:
                f.seek(self.posicao)
                bruto = f.read(st.st_size - self.posicao)
        except OSError:
            return
        fim = bruto.rfind(b"\n")
        if fim < 0:
            return
        self.posicao += fim + 1
        for linha in bruto[:fim].decode("utf-8", errors="replace").splitlines():
            if not any(m in linha for m in ('"session_meta"', '"task_started"', '"task_complete"',
                                             '"token_count"', '"user_message"')):
                continue
            obj = _carregar(linha)
            if not obj:
                continue
            p = obj.get("payload") or {}
            tipo, sub = obj.get("type"), p.get("type")
            if tipo == "session_meta" and not self.meta:
                self.meta = p
            elif tipo == "event_msg" and sub == "task_started":
                self.abertos.add(p.get("turn_id"))
                self.ultimo_inicio = _momento(linha)
            elif tipo == "event_msg" and sub == "task_complete":
                self.abertos.discard(p.get("turn_id"))
                self.ultimo_fim = _momento(linha)
            elif tipo == "event_msg" and sub == "token_count":
                total = (p.get("info") or {}).get("total_token_usage")
                if isinstance(total, dict):
                    self.tokens = total
            elif tipo == "event_msg" and sub == "user_message" and self.titulo is None:
                self.titulo = titulo_codex(p.get("message"))


def titulo_codex(mensagem):
    texto = str(mensagem or "")
    if "## My request:" in texto:
        texto = texto.split("## My request:", 1)[1]
    for linha in texto.splitlines():
        linha = linha.strip().lstrip("#").strip()
        if linha:
            return linha[:90]
    return None


def nome_codex(titulo_banco, titulo_pedido, tid):
    # O título do banco às vezes é o início cru do pedido ("# Files mentioned by the user: ...").
    for candidato in (titulo_codex(titulo_banco), titulo_pedido):
        if candidato and not candidato.lower().startswith("files mentioned"):
            return candidato
    return f"Conversa Codex {tid[:8]}"


_leitores_codex = {}
_titulos_codex = {"chave": None, "titulos": {}}


def titulos_codex():
    """Títulos das conversas, da tabela threads do state_*.sqlite do Codex.

    O banco do Codex nunca é aberto: ele e o -wal são copiados (só leitura) para uma
    pasta temporária quando mudam, e a consulta roda na cópia.
    """
    bancos = sorted(PASTA_CODEX.glob("state_*.sqlite"))
    if not bancos:
        return {}
    banco = bancos[-1]
    origens = [banco, banco.with_name(banco.name + "-wal")]
    chave = tuple((st.st_size, st.st_mtime_ns) if st else None for st in map(estatistica, origens))
    if chave == _titulos_codex["chave"]:
        return _titulos_codex["titulos"]
    destino = Path(tempfile.gettempdir()) / "painel-agentes-codex"
    try:
        destino.mkdir(exist_ok=True)
        for f in destino.glob(banco.name + "*"):
            f.unlink()
        for o in origens:
            if o.exists():
                shutil.copyfile(o, destino / o.name)
        con = sqlite3.connect(destino / banco.name)
        try:
            titulos = {i: t for i, t in con.execute("select id, title from threads") if t}
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        return _titulos_codex["titulos"]
    _titulos_codex.update(chave=chave, titulos=titulos)
    return titulos


def tokens_codex(t):
    if not isinstance(t, dict):
        return None
    return {
        "total": int(t.get("total_tokens") or 0),
        "entrada": int(t.get("input_tokens") or 0),
        "cache": int(t.get("cached_input_tokens") or 0),
        "saida": int(t.get("output_tokens") or 0),
        "raciocinio": int(t.get("reasoning_output_tokens") or 0),
    }


def times_codex(agora, projetos):
    pasta = PASTA_CODEX / "sessions"
    if not pasta.is_dir():
        return []
    conversas = {}
    for arq in pasta.rglob("rollout-*.jsonl"):
        st = estatistica(arq)
        if st is None or agora - st.st_mtime > JANELA_SEGUNDOS:
            continue
        leitor = _leitores_codex.setdefault(str(arq), LeitorCodex())
        leitor.atualizar(arq)
        if not leitor.meta.get("id"):
            continue
        conversas[leitor.meta["id"]] = (arq, st, leitor)

    def situacao(st, leitor, eh_sub):
        escrevendo = agora - st.st_mtime <= ATIVO_SEGUNDOS
        if leitor.abertos:
            if escrevendo:
                return "trabalhando"
            return "parado" if agora - st.st_mtime > PARADO_SEGUNDOS else ("em andamento" if eh_sub else "ocupado")
        return "concluído" if eh_sub else "inativo"

    titulos = titulos_codex() if conversas else {}
    filhos = {}
    for tid, (arq, st, leitor) in conversas.items():
        pai = leitor.meta.get("parent_thread_id")
        if isinstance(leitor.meta.get("source"), dict) and pai:
            filhos.setdefault(pai, []).append(tid)

    times = []
    for tid, (arq, st, leitor) in conversas.items():
        if isinstance(leitor.meta.get("source"), dict) and leitor.meta.get("parent_thread_id") in conversas:
            continue  # subagente: aparece dentro do time do pai
        cwd = str(leitor.meta.get("cwd") or "").replace("\\\\?\\", "")
        projeto = projeto_do_caminho(cwd, projetos) if cwd else None
        agentes = []
        for fid in filhos.get(tid, []):
            farq, fst, fl = conversas[fid]
            tipo_sub = fl.meta.get("source", {}).get("subagent")
            rotulo = tipo_sub.get("other") if isinstance(tipo_sub, dict) else str(tipo_sub)
            ini = _instante(fl.meta.get("timestamp"), tempos_do_arquivo(fst)[0])
            sit = situacao(fst, fl, True)
            # Apelido/papel que o Codex grava no subagente (não conferido com caso real);
            # se começar pelo código da fase ("F1.2 ..."), o subagente conta naquela fase.
            apelido = next((str(fl.meta[k]) for k in ("agent_nickname", "agent_role", "agent_name")
                            if fl.meta.get(k)), None)
            if rotulo == "guardian":
                nome_sub = "guardian (revisor automático do Codex)"
            else:
                nome_sub = apelido or f"subagente {rotulo}"
            agentes.append({
                "nome": nome_sub,
                "fase": codigo_de_fase(nome_sub)[0],
                "situacao": sit,
                "segundo_plano": None,
                "inicio": ini,
                "ultima_escrita": fst.st_mtime,
                "duracao": (fst.st_mtime if sit in TERMINAIS else agora) - ini,
                "bytes": fst.st_size,
                "consumo": None,
                "tokens_codex": tokens_codex(fl.tokens),
            })
        agentes.sort(key=lambda a: a["inicio"])
        sit_gerente = situacao(st, leitor, False)
        gerente = {"situacao": sit_gerente, "nome_sessao": "Codex " + str(leitor.meta.get("originator") or ""),
                   "ultima_escrita": st.st_mtime, "status_desde": None}
        sit_time = situacao_do_time(agentes) if agentes else "encerrado"
        if sit_gerente == "trabalhando":
            sit_time = "trabalhando"
        elif sit_gerente in ("ocupado", "parado") and sit_time == "encerrado":
            sit_time = "em andamento" if sit_gerente == "ocupado" else "parado"
        tokens_sub = [a["tokens_codex"] for a in agentes if a["tokens_codex"]]
        times.append({
            "id": f"codex:{tid}",
            "tipo": "codex",
            "nome": nome_codex(titulos.get(tid), leitor.titulo, tid),
            "sessao": tid,
            "projeto": projeto,
            "criterio_projeto": ["pasta de trabalho da conversa do Codex"] if projeto else [],
            "criterio_confirmado": True,
            "inicio": _instante(leitor.meta.get("timestamp"), tempos_do_arquivo(st)[0]),
            "ultima_escrita": max([st.st_mtime] + [a["ultima_escrita"] for a in agentes]),
            "situacao": sit_time,
            "gerente": gerente,
            "consumo_agentes": None,
            "consumo_gerente": None,
            "tokens_codex": tokens_codex(leitor.tokens),
            "tokens_codex_subagentes": ({k: sum(t[k] for t in tokens_sub) for k in tokens_sub[0]}
                                        if tokens_sub else None),
            "pasta_codex": cwd,
            "medido": {
                "lancados": len(agentes),
                "iniciados": len(agentes),
                "concluidos": sum(1 for a in agentes if a["situacao"] in TERMINAIS),
                "trabalhando": sum(1 for a in agentes if a["situacao"] == "trabalhando"),
                "repetidos": 0,
                "falharam": 0,
            },
            "fases": [],
            "estimativa": {"base": False,
                           "motivo": "Conversa do Codex sem fases declaradas: não há base para estimar."},
            "agentes": agentes,
        })
    return times


# ---------------------------------------------------------------- estado geral

_estado = {"quando": 0, "dados": None}
_estado_lock = threading.Lock()


def _tentar(avisos, rotulo, funcao, *args):
    """Um time com arquivo inesperado vira aviso; nunca derruba o painel inteiro."""
    try:
        return funcao(*args)
    except Exception as erro:
        avisos.append(f"{rotulo}: arquivo em formato inesperado (detalhe técnico: {type(erro).__name__}: {erro})")
        return [] if funcao is times_de_agentes else None


def varrer():
    agora = time.time()
    projetos = listar_projetos()
    times = []
    abertas = sessoes_abertas()
    vistas = set()
    avisos = []
    if PASTA_PROJETOS.is_dir():
        for pasta in PASTA_PROJETOS.iterdir():
            if not pasta.is_dir():
                continue
            for sessao in pasta.iterdir():
                sub = sessao / "subagents"
                ocupada = sessao_ativa(abertas.get(sessao.name))
                if not sub.is_dir() and not ocupada:
                    continue
                if sub.is_dir() or (pasta / (sessao.name + ".jsonl")).is_file():
                    vistas.add(sessao.name)
                times.extend(_tentar(avisos, f"sessão {sessao.name[:8]}", times_de_agentes,
                                     pasta, sessao, sub, agora, projetos, abertas.get(sessao.name)))
                wfs = sub / "workflows"
                if wfs.is_dir():
                    for wf in wfs.iterdir():
                        if wf.is_dir() and wf.name.startswith("wf_"):
                            t = _tentar(avisos, f"workflow {wf.name}", time_de_workflow,
                                        pasta, sessao, wf, agora, projetos,
                                        abertas.get(sessao.name))
                            if t:
                                times.append(t)
        # Sessão ocupada cuja conversa está em outra pasta (ou que nunca lançou agente).
        for sid, registro in abertas.items():
            if sid in vistas or not sessao_ativa(registro):
                continue
            for conversa in PASTA_PROJETOS.glob(f"*/{sid}.jsonl"):
                pasta = conversa.parent
                times.extend(_tentar(avisos, f"sessão {sid[:8]}", times_de_agentes,
                                     pasta, pasta / sid, pasta / sid / "subagents",
                                     agora, projetos, registro))

    times.extend(_tentar(avisos, "Codex", times_codex, agora, projetos) or [])

    com_algum_time = {t["projeto"] for t in times}
    recentes = [t for t in times if not t.get("antigo")]
    recentes.sort(key=lambda t: t["ultima_escrita"], reverse=True)

    try:
        planos = montar_planos(recentes, projetos, agora, avisos)
    except Exception as erro:
        avisos.append(f"planos: arquivo em formato inesperado (detalhe técnico: {type(erro).__name__}: {erro})")
        planos = []

    lista = []
    for nome in projetos:
        seus = [t for t in recentes if t["projeto"] == nome]
        planos_ativos = [p for p in planos if p["projeto"] == nome and p["situacao"] == "em andamento"]
        lista.append({
            "nome": nome,
            "times_recentes": len(seus),
            "algum_time": nome in com_algum_time,
            "trabalhando": any(t["situacao"] == "trabalhando" for t in seus),
            "aguardando": any(t["situacao"] == "aguardando" for t in seus),
            "planos_ativos": len(planos_ativos),
            "ultima_escrita": max([t["ultima_escrita"] for t in seus] +
                                  [p["atualizado_em"] for p in planos_ativos] or [0]) or None,
        })
    # Primeiro quem espera o usuário, depois quem trabalha, depois quem tem time ou plano.
    lista.sort(key=lambda p: (not p["aguardando"], not p["trabalhando"],
                              p["times_recentes"] == 0 and p["planos_ativos"] == 0,
                              -(p["ultima_escrita"] or 0), p["nome"].casefold()))

    return {
        "agora": agora,
        "workspace": str(WORKSPACE),
        "workspace_existe": WORKSPACE.is_dir(),
        "avisos": avisos,
        "aviso_porta": AVISO_PORTA["texto"],
        "versao": VERSAO,
        "ativo_segundos": ATIVO_SEGUNDOS,
        "projetos": lista,
        "times": recentes,
        "planos": planos,
    }


def estado():
    with _estado_lock:
        if _estado["dados"] is None or time.time() - _estado["quando"] > 2:
            _estado["dados"] = varrer()
            _estado["quando"] = time.time()
        return _estado["dados"]


# ---------------------------------------------------------------- servidor

# Arquivos do app instalável (PWA), servidos só por esta lista fechada.
ESTATICOS = {
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/icons/icone.svg": ("icons/icone.svg", "image/svg+xml"),
    "/icons/logo-teklabs.svg": ("icons/logo-teklabs.svg", "image/svg+xml"),
    "/icons/icone-rede.svg": ("icons/icone-rede.svg", "image/svg+xml"),
    "/icons/icone-192.png": ("icons/icone-192.png", "image/png"),
    "/icons/icone-512.png": ("icons/icone-512.png", "image/png"),
    "/icons/icone-maskable-512.png": ("icons/icone-maskable-512.png", "image/png"),
}


class Tratador(BaseHTTPRequestHandler):
    def do_GET(self):
        # Só atende pedidos endereçados a esta máquina (protege contra DNS rebinding).
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in ("127.0.0.1", "localhost"):
            self._responder(403, "text/plain; charset=utf-8", "acesso recusado".encode("utf-8"))
            return
        caminho = urlparse(self.path).path
        if caminho in ("/", "/index.html"):
            corpo = (ler_texto(PASTA_PAINEL / "index.html") or "index.html não encontrado").encode("utf-8")
            self._responder(200, "text/html; charset=utf-8", corpo)
        elif caminho == "/api/saude":
            corpo = json.dumps({"app": APP_ID, "versao": VERSAO}).encode("utf-8")
            self._responder(200, "application/json; charset=utf-8", corpo)
        elif caminho in ESTATICOS:
            nome, tipo = ESTATICOS[caminho]
            try:
                corpo = (PASTA_PAINEL / nome).read_bytes()
            except OSError:
                self._responder(404, "text/plain; charset=utf-8", "não encontrado".encode("utf-8"))
                return
            self._responder(200, tipo, corpo)
        elif caminho == "/api/estado":
            try:
                corpo = json.dumps(estado(), ensure_ascii=False).encode("utf-8")
                self._responder(200, "application/json; charset=utf-8", corpo)
            except Exception as erro:  # o painel nunca deve cair por um arquivo estranho
                corpo = json.dumps({"erro": str(erro)}, ensure_ascii=False).encode("utf-8")
                self._responder(500, "application/json; charset=utf-8", corpo)
        else:
            self._responder(404, "text/plain; charset=utf-8", "não encontrado".encode("utf-8"))

    def _responder(self, codigo, tipo, corpo):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass  # sob pythonw não há console


class Servidor(ThreadingHTTPServer):
    allow_reuse_address = False  # no Windows, reuse permitiria dividir a porta com outro processo
    daemon_threads = True


def porta_em_uso(porta):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as teste:
        teste.settimeout(0.3)
        return teste.connect_ex(("127.0.0.1", porta)) == 0


def porta_livre(inicio=PORTA_INICIAL):
    """Primeira porta livre a partir de `inicio`, confirmada por connect e por bind."""
    porta = inicio
    while porta < 65535:
        if porta not in PORTAS_EVITADAS and not porta_em_uso(porta):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as teste:
                try:
                    teste.bind(("127.0.0.1", porta))
                    return porta
                except OSError:
                    pass
        porta += 1
    raise RuntimeError("nenhuma porta livre encontrada")


def eh_este_painel(porta):
    """True se quem responde na porta é o próprio painel (outra cópia já rodando)."""
    sem_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nunca passar por proxy do sistema
    try:
        with sem_proxy.open(f"http://127.0.0.1:{porta}/api/saude", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_ID
    except (OSError, ValueError):
        return False


AVISO_PORTA = {"texto": None}


def main():
    preferida = int(CONFIG.get("porta") or PORTA_INICIAL)
    if "--sugerir-porta" in sys.argv:
        # usado pelo instalador: a porta configurada se estiver livre ou já for deste painel; senão a próxima livre
        if eh_este_painel(preferida) or not porta_em_uso(preferida):
            print(preferida)
        else:
            print(porta_livre(preferida + 1))
        return
    if porta_em_uso(preferida) and eh_este_painel(preferida):
        if sys.stdout:
            print(f"O painel já está no ar em http://127.0.0.1:{preferida}/", flush=True)
        return  # não abre segunda cópia
    servidor, porta = None, preferida
    while servidor is None:
        try:
            servidor = Servidor(("127.0.0.1", porta), Tratador)
        except OSError:
            # ocupada por outro programa, reservada pelo Windows ou tomada numa corrida: tenta a próxima livre
            porta = porta_livre(porta + 1)
    if porta != preferida:
        AVISO_PORTA["texto"] = (f"A porta {preferida} não está disponível (outro programa ou reserva do sistema); "
                                f"o painel abriu na {porta}. O app instalado aponta para a {preferida}: libere essa "
                                f"porta ou reinstale o app a partir deste endereço.")
    url = f"http://127.0.0.1:{porta}/"
    try:
        (PASTA_PAINEL / "endereco.txt").write_text(url + "\n" + (AVISO_PORTA["texto"] or "") + "\n",
                                                   encoding="utf-8")
    except OSError:
        pass
    if sys.stdout:
        print(f"Painel no ar: {url}  (Ctrl+C para parar)", flush=True)
        if AVISO_PORTA["texto"]:
            print("Aviso: " + AVISO_PORTA["texto"], flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
