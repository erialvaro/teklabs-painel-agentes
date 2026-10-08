<img src="monitor/icons/logo-teklabs.svg" alt="teklabs" width="122" height="44">

**TekLabs Digital** · Open Source Software & AI

# Painel de Agentes · TekLabs Digital

Criado por: [Erick Álvaro da Silva](https://www.linkedin.com/in/erick-silva/) · TekLabs Digital ·
[<img src="docs/linkedin.svg" alt="LinkedIn" width="16" height="16">](https://www.linkedin.com/in/erick-silva/)

Um jeito de trabalhar com IA em times de agentes, e um painel para acompanhar esses times
trabalhando nos seus projetos, no Claude Code e no Codex.

## Como funciona, em resumo

1. **Arquitetura de multiagentes.** Toda demanda segue o fluxo
   **CTO planeja em fases → gerente coordena especialistas → QA valida no fim de cada fase**.
   As regras ficam em `CLAUDE.md` (Claude Code) e `AGENTS.md` (Codex), que os dois leem
   no começo de cada conversa. Elas definem fases pequenas, QA com orçamento, modelo do
   tamanho da tarefa e confirmação antes de qualquer ação destrutiva, para gastar menos
   tokens sem perder a validação.
2. **Permissões do Claude Code.** O dia a dia (comandos, leitura e edição de arquivos)
   deixa de pedir "yes" a cada passo; ações destrutivas (apagar arquivos, `git push --force`,
   `DROP TABLE`, apagar recursos na nuvem e outras) continuam pedindo confirmação.
3. **Painel local.** Um servidor Python (só biblioteca padrão) que lê os arquivos das
   conversas do Claude Code e do Codex e mostra, por projeto: times, agentes, fases do
   plano, quem está trabalhando agora, tempo e tokens gastos. Ele **só lê**: não altera nada
   nas pastas do Claude Code nem do Codex, e escuta apenas em `127.0.0.1` (ninguém de fora
   acessa). Pode ser instalado como app no desktop (PWA).

## Instalação

Requisito: Python 3.9 ou mais novo.

```bash
git clone <endereço do repositório> teklabs-painel-agentes
cd teklabs-painel-agentes
```

- **Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\install.ps1`
- **macOS e Linux:** `bash install.sh`

O instalador explica cada passo e **pergunta antes de mexer em cada arquivo existente**.
Todo arquivo substituído ganha uma cópia de segurança com data (`.bak-AAAAMMDD-HHMMSS`).

| O que | Onde | Como |
|---|---|---|
| Regras de multiagentes (Claude Code) | `~/.claude/CLAUDE.md` | substitui, com backup, se você aceitar |
| Permissões (Claude Code) | `~/.claude/settings.json` | mescla só `permissions`; o resto do arquivo fica como está |
| Regras de multiagentes (Codex) | `~/.codex/AGENTS.md` | substitui, com backup, se você aceitar |
| Painel | `~/.claude/monitor/` | copia os arquivos e grava `config.json` (pasta da workspace e porta) |
| Abrir junto com o sistema | pasta de inicialização (Windows), LaunchAgent (macOS), autostart (Linux) | só se você aceitar |

O instalador **nunca** toca em `auth.json`, `config.toml` do Codex, credenciais ou
históricos de conversa.

Depois de instalado, abra o endereço mostrado (por padrão `http://127.0.0.1:8765/`) e, no
Chrome ou Edge, use **Instalar app** na barra de endereço para ter o painel no desktop.

## Porta

O instalador escolhe uma porta livre (começando em 8765 e pulando portas comuns de
frameworks e bancos) e a grava em `~/.claude/monitor/config.json`. O app instalado fica
preso a esse endereço; se outro programa ocupar a porta depois, o painel abre na próxima
livre e avisa na tela.

## Documentação do painel

Veja [monitor/README.md](monitor/README.md): o que cada número significa (medido,
informado pelo gerente ou estimado), Codex, tokens e planos.

---

Licença [MIT](LICENSE): uso, cópia e modificação livres, mantendo o aviso de autoria.
© 2026 Erick Álvaro da Silva · TekLabs Digital.
