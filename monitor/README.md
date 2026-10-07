<img src="icons/logo-teklabs.svg" alt="teklabs" width="122" height="44">

**TekLabs Digital** · Open Source Software & AI

# Painel de Agentes · TekLabs Digital

Criado por: [Erick Álvaro da Silva](https://www.linkedin.com/in/erick-silva/) · TekLabs Digital ·
[<img src="../docs/linkedin.svg" alt="LinkedIn" width="16" height="16">](https://www.linkedin.com/in/erick-silva/)

Página local para acompanhar os times de agentes do Claude Code e do Codex
trabalhando nos projetos da workspace. Usa só Python (biblioteca padrão) e um
arquivo HTML.

O painel **só lê arquivos**. Ele não cria, não altera e não trava nada nas pastas
do Claude Code (`~/.claude/projects`, `~/.claude/sessions`) nem do Codex
(`~/.codex`). Abrir ou fechar o painel não interfere em quem está trabalhando. Ele
grava apenas `endereco.txt` (a URL em uso) nesta pasta e uma cópia temporária do
banco de títulos do Codex na pasta temporária do sistema.

## Como abrir

O instalador já deixa tudo pronto (e, se você aceitar, abre o painel junto com o
sistema). Para abrir à mão:

- **Windows:** `pythonw "%USERPROFILE%\.claude\monitor\painel.py"` (sem janela) ou
  `python ...` (com mensagens na tela).
- **macOS e Linux:** `python3 ~/.claude/monitor/painel.py &`

O endereço fica em `~/.claude/monitor/endereco.txt` (normalmente
`http://127.0.0.1:8765/`). O painel escuta só neste computador (127.0.0.1). Se ele
já estiver rodando, uma segunda abertura não cria outra cópia.

## Configuração (`config.json`)

O instalador grava `~/.claude/monitor/config.json`:

```json
{"workspace": "C:/caminho/da/sua/workspace", "porta": 8765}
```

- **workspace**: pasta com um projeto por subpasta (pastas que começam com ponto
  não entram). A variável de ambiente `MONITOR_WORKSPACE`, se existir, tem
  prioridade.
- **porta**: fixa, porque o app instalado (PWA) fica preso ao endereço. Se outro
  programa ocupar essa porta, o painel abre na próxima livre e mostra um aviso.

Depois de mudar o arquivo, feche e abra o painel.

## Como parar

- **Windows (PowerShell):**
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*monitor*painel.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId }
  ```
- **macOS e Linux:** `pkill -f "monitor/painel.py"`

## Telas

1. **Projetos**: todos os projetos da workspace. Primeiro vem quem tem um
   gerente esperando você (por exemplo, um pedido de permissão), depois quem tem
   time trabalhando; quem não teve time aparece apagado com "nenhum time ainda"
   (ou "nenhum time nos últimos 7 dias", se só teve times antigos).
2. **Detalhe do projeto** (clique no cartão): cada time dos últimos 7 dias, com
   fases, números e a tabela de agentes.

A página se atualiza sozinha a cada 5 segundos.

## Codex

O painel também mostra as conversas do Codex (extensão do VS Code e Codex
Desktop) desta máquina, lendo só os arquivos
`%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl` (ou `%CODEX_HOME%`). Os bancos
sqlite do Codex nunca são abertos: para pegar o título das conversas, o painel
copia o `state_*.sqlite` (e o `-wal`) para a pasta temporária do Windows
(`%TEMP%\painel-agentes-codex`) quando ele muda e consulta só a cópia.

- **Time Codex** = uma conversa principal do Codex. Ela aparece no projeto da
  pasta de trabalho dela; conversa aberta na raiz da workspace ou fora dela vai
  para "Sem projeto identificado", com a pasta mostrada.
- **Gerente**: a própria conversa. "trabalhando" = tarefa aberta e escrita nos
  últimos 90 s; "ocupado" = tarefa aberta sem escrita recente; "sem tarefa em
  andamento" = a última tarefa terminou.
- **Agentes**: os subagentes que o Codex cria, ligados à conversa pelo
  `parent_thread_id`. Os mais comuns são os "guardian", revisores automáticos
  que o Codex cria para aprovar ações. O nome do subagente vem do apelido ou do
  papel que o Codex grava; se começar pelo código da fase (`F1.2 ...`), ele é
  contado naquela fase do plano. Essa ligação com fases ainda não foi conferida
  com um subagente real criado por demanda no Codex.
- **Tokens (contagem do Codex)**: total acumulado da conversa, com entrada,
  cache e saída no detalhe. **Não é comparável** com o "Tokens (equiv.)" do
  Claude: são modelos e preços diferentes.
- Conversas do Codex na nuvem ou em outra máquina não aparecem: não há arquivo
  delas aqui.

## Tokens (medido)

Cada resposta de um agente grava no arquivo dele quantos tokens usou. O painel
soma por agente, por time, por fase do plano e pela conversa do gerente:

- **Tokens (equiv.)**: tokens equivalentes de entrada = entrada + 1,25 × cache
  criado + 0,1 × cache lido + 5 × saída. Os pesos são a proporção de preço,
  igual em todos os modelos Claude; serve para comparar custo entre agentes.
  Não é valor em dinheiro: o preço por token muda de modelo para modelo.
- Passe o mouse no número para ver chamadas, entrada, cache criado, cache
  lido, saída e quantas chamadas foram de cada modelo.
- **Conversa do gerente (inteira)**: soma da sessão toda do gerente, não só do
  time; costuma ser o maior custo.

## Plano da demanda (fases do CTO)

Quando o CTO planeja uma demanda em fases (regra do `CLAUDE.md` global), ele
grava o plano em `%USERPROFILE%\.claude\monitor\planos\*.json`. O painel mostra
esse plano no topo do projeto:

- **Situação de cada fase e subfase** (pendente, em andamento, em QA,
  aprovada): **informada pelo gerente** no arquivo do plano. Aparece em bloco
  cinza, separado do que é medido.
- **Agentes por fase** (medido): cada agente cujo nome começa pelo código da
  fase (`F1.2 Especialista ...`, `QA F1`) é contado naquela fase. O agente vai
  para o plano mais recente do mesmo projeto criado antes dele.
- **Estimativa**:
  - tempo restante = tempo desde a criação do plano ÷ fases aprovadas × fases
    que faltam;
  - total de agentes = agentes já ligados às fases + (média de agentes das
    fases aprovadas × fases ainda pendentes).
  Sem nenhuma fase aprovada: "sem base para estimar ainda". Cada agente conta
  numa fase só (a de código mais específico: `F1.10 ...` conta em F1.10, não em F1).

Plano com projeto que não existe na workspace, ou com arquivo inválido, gera um
aviso amarelo. Planos concluídos ou cancelados somem depois de 7 dias sem
atualização.

## O que cada número significa

### Medido (lido dos arquivos, fundo liso, azul)

| Na tela | De onde vem |
|---|---|
| agentes iniciados / lançados | agentes avulsos: quantos arquivos de agente existem no time. Workflow: "lançados" são os que o registro do motor mostra, incluindo os que ainda estão na fila; "já começaram" são os que de fato iniciaram |
| encerrados | agentes com aviso de conclusão gravado; em workflow, também os "repetidos" |
| trabalhando agora | agentes cujo arquivo foi escrito nos últimos 90 segundos (ponto pulsando) |
| barra de agentes avulsos | encerrados dividido por iniciados. **Não é o progresso do trabalho todo**, porque o gerente pode iniciar mais agentes |
| fases | "feita" só quando todos os agentes da fase encerraram; "atual" enquanto a fase tem agente aberto (ou é a última a receber agentes); "ainda não começou" quando nenhum agente dela foi lançado. Fase pulada pelo roteiro aparece como feita, com 0 agentes, e não entra na média da estimativa |
| começou | data de criação do arquivo do agente |
| tempo | da criação do arquivo até a última escrita (ou até agora, se ainda não encerrou) |
| última escrita | data da última gravação no arquivo do agente |
| quanto escreveu | tamanho do arquivo de conversa do agente |

Linha **Gerente** (times de agentes avulsos): a situação da conversa que
coordena o time, lida do registro de sessões abertas do Claude Code
(`%USERPROFILE%\.claude\sessions\*.json`) e da última escrita na conversa.

- **trabalhando**: sessão ocupada e a conversa foi escrita nos últimos 90 segundos.
- **ocupado, sem escrever agora**: sessão ocupada, mas sem escrita recente (por exemplo, esperando um comando).
- **ocioso, aguardando você**: sessão aberta, esperando a sua próxima mensagem.
- **aguardando você (pedido de permissão)**: a sessão parou esperando você aprovar uma ação no Claude Code. O time não avança até você responder. Nesse caso o time inteiro aparece como "aguardando você" e o projeto vai para o topo da lista.
- **sessão fechada**: a sessão não está no registro de sessões abertas.

Quando o gerente está trabalhando, o time inteiro conta como "trabalhando" e o
projeto sobe para o topo da lista, mesmo sem nenhum especialista ativo. Uma
sessão ocupada que ainda não lançou nenhum agente também aparece, com a nota
"nenhum especialista lançado ainda".

Situações de um agente:

- **trabalhando**: escreveu nos últimos 90 segundos e ainda não tem aviso de conclusão (ou voltou a escrever depois do aviso, porque foi retomado).
- **em andamento, sem escrever agora**: não encerrou e está há menos de 30 min sem escrever (por exemplo, esperando um comando demorado).
- **parado, sem sinal de conclusão**: não encerrou e está há mais de 30 min sem escrever.
- **concluído**, **falhou**, **interrompido**: conforme o aviso gravado na conversa do gerente.
- **repetido** (só workflow): o motor repetiu o agente e outra tentativa com a mesma chave concluiu.
- **na fila** (só workflow): lançado, ainda não começou.

### Estimativa (fundo roxo tracejado)

O total de agentes de um time não está gravado em lugar nenhum. Por isso
porcentagem e tempo restante são **estimativas**:

- total estimado = agentes já lançados (inclusive os que estão na fila) +
  (média de agentes por fase já concluída × fases que ainda não começaram),
  arredondado para o inteiro mais próximo;
- porcentagem = encerrados ÷ total estimado;
- tempo restante = tempo decorrido ÷ encerrados × agentes que faltam.

Se nenhuma fase terminou, a tela mostra "sem base para estimar ainda". Times de
agentes avulsos não têm fases, então nunca têm estimativa.

## Como o painel sabe de qual projeto é cada time

O time pode ser disparado de uma conversa aberta na raiz da workspace e ainda
assim trabalhar num projeto, então a pasta da conversa não serve sozinha. A
ordem usada:

1. **Agentes avulsos**: a pasta de trabalho (`cwd`) gravada nas linhas do
   arquivo de cada agente. Conferido nos arquivos reais.
2. **Workflow**: caminho absoluto de um projeto da workspace citado no roteiro
   (`.js`); se não houver, o `cwd` dos agentes.
3. Último recurso: o nome da pasta da sessão, comparado com os nomes das pastas
   reais da workspace convertidos do mesmo jeito (caracteres que não são letra
   ou número viram hífen), escolhendo a correspondência mais longa, sem
   diferenciar maiúsculas.

Times que não caem em nenhum projeto aparecem no cartão "Sem projeto
identificado".

## Quando algo não pode ser lido

Se um time tiver algum arquivo em formato inesperado, só esse time fica de
fora e a página mostra um aviso amarelo dizendo qual sessão foi. O resto do
painel continua funcionando. Se uma atualização falhar, a página mantém os
últimos dados bons e avisa de quando eles são.

## Formatos lidos e o que foi conferido

Na tela, "agentes avulsos" são os times montados com a ferramenta Agent e
"time com roteiro" é o workflow.

- **Agentes avulsos** (ferramenta Agent): `<sessao>\subagents\agent-<id>.jsonl`,
  `agent-<id>.meta.json` (nome do agente) e a conversa do gerente
  `<sessao>.jsonl` (título do time e avisos de conclusão). **Conferido** em
  30/09/2026 com um time real.
- **Workflows**: `<sessao>\subagents\workflows\wf_<runId>\journal.jsonl`,
  `agent-*.jsonl`, `agent-*.meta.json` e o roteiro `*<runId>.js`.
  **Conferido** em 02/10/2026 com um workflow real:
  - o roteiro fica em `<pasta do projeto>\<sessao>\workflows\scripts\`, que pode
    ser outra pasta de `.claude\projects`, não a da execução; o painel procura
    em todas pelo id da sessão;
  - o evento `launched` é um só por workflow, sem agentId; os agentes aparecem
    pelo `started` (com agentId, label, phase e key);
  - o projeto sai do caminho absoluto citado no roteiro (confere com o `cwd` dos agentes).
  - **Ainda não visto**: o evento `result`. Se ele vier sem agentId, o painel
    atribui ao último agente iniciado com a mesma key.
