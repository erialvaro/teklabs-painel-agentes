"""Instalador do Painel de Agentes · TekLabs Digital (Windows, macOS e Linux).

Criado por Erick Álvaro da Silva · TekLabs Digital.
Só biblioteca padrão do Python 3.9+. Explica cada passo e pergunta antes de mexer em
qualquer arquivo existente; todo arquivo substituído ganha cópia .bak-AAAAMMDD-HHMMSS.

Uso:  python instalar.py [--sim] [--home PASTA] [--workspace PASTA]
                         [--sem-inicio-automatico] [--nao-abrir]
  --sim                   responde "sim" a todas as perguntas (automação e testes)
  --home                  pasta do usuário de destino (padrão: a do usuário atual)
  --workspace             pasta com um projeto por subpasta
  --sem-inicio-automatico não configura o painel para abrir com o sistema
  --nao-abrir             não abre o painel ao final
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parent
SISTEMA = platform.system()  # Windows, Darwin ou Linux
CARIMBO = datetime.now().strftime("%Y%m%d-%H%M%S")
ARQUIVOS_PAINEL = ["painel.py", "index.html", "manifest.webmanifest", "sw.js", "README.md",
                   "icons/icone.svg", "icons/icone-rede.svg", "icons/logo-teklabs.svg",
                   "icons/icone-192.png", "icons/icone-512.png",
                   "icons/icone-maskable-512.png"]

RESUMO = """
  Painel de Agentes · TekLabs Digital (Open Source Software & AI)
  Criado por: Erick Álvaro da Silva · TekLabs Digital · linkedin.com/in/erick-silva

  Como funciona, em resumo:
  1. Arquitetura de multiagentes: toda demanda segue "CTO planeja em fases, gerente
     coordena especialistas, QA valida no fim de cada fase". As regras ficam no
     CLAUDE.md (Claude Code) e no AGENTS.md (Codex), que os dois leem ao começar cada
     conversa. Isso reduz retrabalho e gasto de tokens sem perder a validação.
  2. Permissões do Claude Code: o dia a dia deixa de pedir "yes" a cada passo; ações
     destrutivas (apagar arquivos, git push --force, DROP TABLE, apagar recursos na
     nuvem e outras) continuam pedindo confirmação.
  3. Painel local: mostra, por projeto, os times de agentes do Claude Code e do Codex,
     as fases do plano, quem está trabalhando, tempo e tokens. Só lê arquivos e escuta
     apenas neste computador (127.0.0.1). Pode virar app no desktop.

  Nada é alterado sem a sua confirmação. Credenciais, históricos de conversa e o
  config.toml do Codex nunca são tocados.
"""


class Instalador:
    def __init__(self, args):
        self.sim = args.sim
        self.home = Path(args.home).expanduser().resolve() if args.home else Path.home()
        self.workspace_arg = args.workspace
        self.inicio_auto = not args.sem_inicio_automatico
        self.abrir = not args.nao_abrir
        self.claude = self.home / ".claude"
        self.codex = self.home / ".codex"
        self.monitor = self.claude / "monitor"
        self.feito, self.pulado, self.backups = [], [], []

    # ------------------------------------------------------------ conversa com o usuário
    def perguntar(self, texto, padrao=True):
        if self.sim:
            print(f"{texto} [{'S/n' if padrao else 's/N'}] s (automático)")
            return True
        opcoes = "S/n" if padrao else "s/N"
        while True:
            try:
                r = input(f"{texto} [{opcoes}] ").strip().lower()
            except EOFError:
                # sem ninguém respondendo, nunca altera nada: EOF conta como "não"
                print("\n  (sem resposta: tratado como não)")
                return False
            if not r:
                return padrao
            if r in ("s", "sim", "y", "yes"):
                return True
            if r in ("n", "nao", "não", "no"):
                return False

    def ler(self, texto, padrao):
        if self.sim:
            return padrao
        try:
            r = input(f"{texto} [{padrao}]: ").strip()
        except EOFError:
            return padrao
        return r or padrao

    @staticmethod
    def titulo(texto):
        print("\n" + texto + "\n" + "-" * len(texto))

    # ------------------------------------------------------------ utilidades de arquivo
    def backup(self, arq):
        destino = arq.with_name(f"{arq.name}.bak-{CARIMBO}")
        shutil.copy2(arq, destino)
        self.backups.append(destino)
        return destino

    def instalar_arquivo(self, origem, destino, nome, explicacao):
        self.titulo(nome)
        print(explicacao)
        novo = origem.read_bytes()
        if destino.exists():
            if destino.read_bytes() == novo:
                print(f"  {destino} já está igual à versão do projeto. Nada a fazer.")
                self.pulado.append(f"{nome}: já atualizado")
                return
            print(f"  Já existe {destino} com conteúdo diferente.")
            print("  Se você aceitar, ele é guardado como cópia de segurança e substituído.")
            print("  Se recusar, nada muda e esta parte do projeto não vale nesta ferramenta.")
            if not self.perguntar("  Substituir (com cópia de segurança)?", padrao=False):
                self.pulado.append(f"{nome}: mantido o arquivo existente")
                return
            print(f"  Cópia de segurança: {self.backup(destino)}")
        elif not self.perguntar(f"  Criar {destino}?"):
            self.pulado.append(f"{nome}: não instalado")
            return
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(novo)
        self.feito.append(f"{nome}: {destino}")

    # ------------------------------------------------------------ passos
    def passo_claude_md(self):
        self.instalar_arquivo(
            RAIZ / "config" / "claude" / "CLAUDE.md", self.claude / "CLAUDE.md",
            "1. Regras de multiagentes no Claude Code (CLAUDE.md)",
            "  O Claude Code lê este arquivo no começo de toda conversa, em todos os projetos.\n"
            "  É ele que faz o Claude planejar em fases, usar especialistas e chamar o QA no\n"
            "  fim de cada fase, com as regras de economia de tokens.")

    def passo_permissoes(self):
        self.titulo("2. Permissões do Claude Code (settings.json)")
        print("  Libera o trabalho do dia a dia sem pedir \"yes\" a cada comando e mantém a\n"
              "  pergunta para ações destrutivas. Só a parte \"permissions\" é mesclada; o resto\n"
              "  do arquivo (modelo, tema, plugins) fica como está.")
        modelo = json.loads((RAIZ / "config" / "claude" / "permissoes.json").read_text(encoding="utf-8"))
        arq = self.claude / "settings.json"
        atual = {}
        if arq.exists():
            try:
                atual = json.loads(arq.read_text(encoding="utf-8"))
                if not isinstance(atual, dict):
                    raise ValueError
            except ValueError:
                print(f"  {arq} não é um JSON válido. Por segurança, ele não será alterado.")
                self.pulado.append("Permissões: settings.json inválido, não alterado")
                return
        perms = atual.setdefault("permissions", {})
        formato_ok = isinstance(perms, dict) and all(
            isinstance(perms.get(k, []), list) for k in ("allow", "ask"))
        if not formato_ok:
            print(f"  A parte \"permissions\" de {arq} está num formato inesperado. Por segurança,\n"
                  "  o arquivo não será alterado; as permissões podem ser ajustadas à mão depois.")
            self.pulado.append("Permissões: formato inesperado em settings.json, não alterado")
            return
        novos = {}
        for chave in ("allow", "ask"):
            lista = perms.setdefault(chave, [])
            faltam = [r for r in modelo["permissions"][chave] if r not in lista]
            novos[chave] = faltam
            lista.extend(faltam)
        if not novos["allow"] and not novos["ask"]:
            print("  As permissões do projeto já estão todas presentes. Nada a fazer.")
            self.pulado.append("Permissões: já atualizadas")
            return
        print(f"  Serão acrescentadas {len(novos['allow'])} liberações e {len(novos['ask'])} perguntas "
              f"de confirmação (nenhuma regra existente é removida).")
        if not self.perguntar("  Mesclar as permissões" + (" (com cópia de segurança)?" if arq.exists() else "?"),
                              padrao=arq.exists() is False):
            self.pulado.append("Permissões: não alteradas")
            return
        if arq.exists():
            print(f"  Cópia de segurança: {self.backup(arq)}")
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(atual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.feito.append(f"Permissões mescladas: {arq}")

    def passo_agents_md(self):
        if not self.codex.exists():
            print(f"\n  (O Codex não parece instalado: {self.codex} não existe.)")
        self.instalar_arquivo(
            RAIZ / "config" / "codex" / "AGENTS.md", self.codex / "AGENTS.md",
            "3. Regras de multiagentes no Codex (AGENTS.md)",
            "  O Codex lê este arquivo no começo de toda conversa. Ele traz a mesma\n"
            "  arquitetura do CLAUDE.md, adaptada ao Codex.")

    def escolher_workspace(self):
        config = self.monitor / "config.json"
        anterior = None
        if config.exists():
            try:
                anterior = json.loads(config.read_text(encoding="utf-8")).get("workspace")
            except ValueError:
                pass
        if self.workspace_arg:
            ws = Path(self.workspace_arg).expanduser()
            if ws.is_dir():
                return ws.resolve()
            print(f"  A pasta informada em --workspace não existe: {ws}")
        sugestao = anterior or str(RAIZ.parent)
        while True:
            print("  A workspace é a pasta onde ficam seus projetos, um por subpasta.")
            ws = Path(self.ler("  Pasta da workspace", sugestao)).expanduser()
            if ws.is_dir():
                return ws.resolve()
            print(f"  A pasta {ws} não existe.")
            if self.sim:
                print(f"  Usando a pasta do usuário ({self.home}); ajuste depois em config.json.")
                return self.home

    def python_do_painel(self):
        exe = Path(sys.executable)
        if SISTEMA == "Windows":
            sem_janela = exe.with_name("pythonw.exe")
            return sem_janela if sem_janela.exists() else exe
        return exe

    def passo_painel(self):
        self.titulo("4. Painel local (~/.claude/monitor)")
        print("  Copia o painel. Seus planos e o config.json existentes são preservados.")
        diferentes = [a for a in ARQUIVOS_PAINEL
                      if not (self.monitor / a).exists()
                      or (self.monitor / a).read_bytes() != (RAIZ / "monitor" / a).read_bytes()]
        if not diferentes:
            print("  O painel já está na versão do projeto.")
        else:
            existentes = [a for a in diferentes if (self.monitor / a).exists()]
            if existentes:
                print(f"  {len(existentes)} arquivo(s) do painel serão atualizados (com cópia de segurança).")
            if not self.perguntar("  Instalar ou atualizar o painel?"):
                self.pulado.append("Painel: não instalado")
                return False
            for a in diferentes:
                destino = self.monitor / a
                destino.parent.mkdir(parents=True, exist_ok=True)
                if destino.exists():
                    self.backup(destino)
                shutil.copy2(RAIZ / "monitor" / a, destino)
            self.feito.append(f"Painel: {len(diferentes)} arquivo(s) em {self.monitor}")
        (self.monitor / "planos").mkdir(parents=True, exist_ok=True)

        ws = self.escolher_workspace()
        config_arq = self.monitor / "config.json"
        config = {}
        if config_arq.exists():
            try:
                config = json.loads(config_arq.read_text(encoding="utf-8"))
                if not isinstance(config, dict):
                    raise ValueError
            except ValueError:
                print(f"  {config_arq} estava inválido; cópia de segurança: {self.backup(config_arq)}")
                config = {}
        config["workspace"] = str(ws)
        config_arq.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        # a porta é escolhida pelo próprio painel: a configurada se livre ou dele mesmo; senão a próxima livre
        r = subprocess.run([sys.executable, str(self.monitor / "painel.py"), "--sugerir-porta"],
                           capture_output=True, text=True, timeout=60)
        porta = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 8765
        config["porta"] = porta
        config_arq.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Workspace: {ws}")
        print(f"  Porta: {porta} (fixa, para o app instalado não mudar de endereço)")
        self.feito.append(f"Configuração do painel: workspace {ws}, porta {porta}")
        return True

    def passo_inicio_automatico(self):
        if not self.inicio_auto:
            return
        self.titulo("5. Abrir o painel junto com o sistema")
        py, painel = self.python_do_painel(), self.monitor / "painel.py"
        if SISTEMA == "Windows":
            # com --home de teste, nunca escreve na pasta de inicialização real
            usa_real = self.home == Path.home() and os.environ.get("APPDATA")
            appdata = Path(os.environ["APPDATA"]) if usa_real else self.home / "AppData" / "Roaming"
            destino = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "TekLabs Painel de Agentes.vbs"
            conteudo = ('Set s = CreateObject("WScript.Shell")\r\n'
                        f's.Run """{py}"" ""{painel}""", 0, False\r\n')
            codificacao = "utf-16"  # o Windows Script Host só lê acentos (ex.: C:\Users\José) em UTF-16 com BOM
        elif SISTEMA == "Darwin":
            destino = self.home / "Library" / "LaunchAgents" / "digital.teklabs.painel-agentes.plist"
            conteudo = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>digital.teklabs.painel-agentes</string>
  <key>ProgramArguments</key><array><string>{escape(str(py))}</string><string>{escape(str(painel))}</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
"""
        else:
            xdg = os.environ.get("XDG_CONFIG_HOME") if self.home == Path.home() else None
            destino = (Path(xdg) if xdg else self.home / ".config") / "autostart" / "teklabs-painel-agentes.desktop"
            conteudo = ("[Desktop Entry]\nType=Application\nName=TekLabs Painel de Agentes\n"
                        f'Exec="{py}" "{painel}"\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n')
        if SISTEMA != "Windows":
            codificacao = "utf-8"
        print(f"  Cria {destino}, que abre o painel (sem janela) quando você entra no sistema.")
        dados = conteudo.encode(codificacao)  # bytes: compara e grava sem conversão de fim de linha
        if destino.exists() and destino.read_bytes() == dados:
            print("  Já está configurado.")
            return
        if not self.perguntar("  Configurar a abertura automática?"):
            self.pulado.append("Abertura automática: não configurada")
            return
        try:
            if destino.exists():
                self.backup(destino)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(dados)
        except OSError as erro:
            print(f"  Não foi possível criar {destino} ({erro}). O painel pode ser aberto à mão.")
            self.pulado.append("Abertura automática: falhou ao gravar")
            return
        self.feito.append(f"Abertura automática: {destino}")

    def passo_abrir(self):
        if not self.abrir:
            return
        self.titulo("6. Abrindo o painel")
        painel = self.monitor / "painel.py"
        if not painel.exists():
            print("  O painel não foi instalado; nada a abrir.")
            return
        py = self.python_do_painel()
        nulo = subprocess.DEVNULL
        if SISTEMA == "Windows":
            subprocess.Popen([str(py), str(painel)], stdout=nulo, stderr=nulo, stdin=nulo,
                             creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        else:
            subprocess.Popen([str(py), str(painel)], stdout=nulo, stderr=nulo, stdin=nulo,
                             start_new_session=True)
        endereco = self.monitor / "endereco.txt"
        for _ in range(20):
            time.sleep(0.5)
            if endereco.exists():
                break
        texto = endereco.read_text(encoding="utf-8", errors="replace").strip() if endereco.exists() else ""
        porta = json.loads((self.monitor / "config.json").read_text(encoding="utf-8")).get("porta", 8765)
        print(f"  Painel no ar: {texto.splitlines()[0] if texto else f'http://127.0.0.1:{porta}/'}")
        print("  No Chrome ou no Edge, use \"Instalar app\" na barra de endereço para tê-lo no desktop.")

    def resumo(self):
        self.titulo("Resumo")
        for f in self.feito:
            print("  feito:   " + f)
        for p in self.pulado:
            print("  sem mudança: " + p)
        if self.backups:
            print("  Cópias de segurança (para desfazer, renomeie de volta):")
            for b in self.backups:
                print("    " + str(b))
        print("\n  As regras novas valem nas conversas abertas a partir de agora no Claude Code e no Codex.")

    def executar(self):
        print(RESUMO)
        if sys.version_info < (3, 9):
            print("É preciso Python 3.9 ou mais novo.")
            return 1
        print(f"  Sistema: {SISTEMA} · Pasta do usuário: {self.home}")
        if not self.perguntar("\nContinuar com a instalação?"):
            print("Nada foi alterado.")
            return 0
        self.passo_claude_md()
        self.passo_permissoes()
        self.passo_agents_md()
        if self.passo_painel():
            self.passo_inicio_automatico()
            self.passo_abrir()
        self.resumo()
        return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Instalador do Painel de Agentes · TekLabs Digital")
    p.add_argument("--sim", action="store_true")
    p.add_argument("--home")
    p.add_argument("--workspace")
    p.add_argument("--sem-inicio-automatico", action="store_true")
    p.add_argument("--nao-abrir", action="store_true")
    sys.exit(Instalador(p.parse_args()).executar())


if __name__ == "__main__":
    main()
