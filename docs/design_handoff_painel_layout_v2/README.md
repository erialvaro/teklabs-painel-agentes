# Handoff: Painel de Agentes — layout v2 (casca + tela do projeto)

## Visão geral
Atualização **somente visual/de layout** do arquivo `monitor/index.html` do repositório `teklabs-painel-agentes`. Muda:
1. a **casca** da página (cabeçalho, marca do painel, assinatura do criador, legenda, atualização);
2. a **tela de lista de projetos** (`telaLista()`);
3. a **tela de detalhe do projeto** (`telaProjeto()`, `blocoPlano()`, `blocoMedido()`, `blocoEstimativa()`, `blocoFases()`, `tabelaAgentes()`).

**Não muda:** `painel.py`, o contrato de `/api/estado`, as regras de situação (`TEXTO_SITUACAO`, `CLASSE_SITUACAO`), os cálculos, os textos explicativos, o service worker, o manifest e o ciclo de atualização (5 s / 1 s). **Sem barra lateral** — decisão explícita do dono do projeto.

## Sobre os arquivos de design
Os arquivos em `referencia/` são **referências de design feitas em HTML** (protótipo com dados fictícios), não código para copiar. A tarefa é **recriar esse layout dentro do `monitor/index.html` existente**, mantendo a arquitetura atual: HTML único, CSS em `<style>` com variáveis em `:root`, JS puro gerando strings e `innerHTML`, rotas por hash (`#/` e `#/projeto/<nome>`). Não introduza framework, build nem dependências.

Para abrir a referência: sirva a pasta `referencia/` por HTTP (ex.: `python -m http.server` dentro dela) e abra `Painel de Agentes v2.dc.html`.

## Fidelidade
**Alta fidelidade.** Cores, tamanhos, raios, espaçamentos e textos abaixo são finais. Mantenha a fonte atual (`"Segoe UI", system-ui, -apple-system, sans-serif`).

---

## Casca

### Cabeçalho superior (substitui `.marca` + `<header>` + `.legenda`)
- `position: sticky; top: 0; z-index: 5`, fundo `#0b1f3a` (mesmo `theme-color` do manifest), `box-shadow: 0 1px 0 rgba(255,255,255,.06)`.
- Container interno: `max-width: 1240px; margin: 0 auto; padding: 12px 32px; display:flex; align-items:center; gap:16px; flex-wrap:wrap`.
- **Esquerda — marca (link para `#/`)**: `display:flex; gap:12px`.
  - Ícone `assets/icone-rede.svg` 38×38 (novo ícone do painel: nó central em degradê `#5b7cff→#a78bfa` ligado a três agentes; um ciano `#22d3ee`, dois `#e2e8f0`).
  - Coluna (`gap:4px`):
    - "Painel de Agentes" — 16px, peso 700, `#fff`, `line-height:1.1`, `letter-spacing:-.01em`, `white-space:nowrap`.
    - Linha 11px `#8fa3bd`, `gap:6px`: "por" + `logo-teklabs.svg` em 47×17 + "Open Source Software & AI".
- Espaçador `flex:1`.
- **Direita — status e legenda** (`gap:8px`, 12.5px, `position:relative`):
  - Pílula de status: `border:1px solid rgba(255,255,255,.14); border-radius:999px; padding:5px 12px; color:#dbe4f0`. Ponto verde 7px `#4ade80` com o pulso existente (`@keyframes pulso`). Texto vem de `atualizarStatus()` ("atualizado há N s" / mensagens de erro). Em erro, troque o ponto para `#f87171`.
  - Botão "Legenda" (ícone de interrogação 13px + texto), mesma pílula; fundo `rgba(255,255,255,.12)` quando aberto; hover `border-color: rgba(255,255,255,.35)`.
  - **Popover da legenda** (abre/fecha no clique; fecha com clique fora ou Esc): `position:absolute; top:calc(100% + 10px); right:0; width:340px; background:#fff; border:1px solid #e2e5ea; border-radius:12px; box-shadow:0 14px 36px rgba(11,31,58,.22); padding:14px 16px; gap:10px; font-size:13px; color:#1b1f24`. Quatro linhas (amostra 26×9px + texto), com os **mesmos textos** de `.legenda` hoje, rótulo em negrito:
    - **Medido:** lido dos arquivos agora (amostra `#2563eb`)
    - **Estimativa:** cálculo aproximado, pode mudar (tracejado `#7c3aed`)
    - **Informado pelo gerente:** situação das fases no plano (`#eef0f3` borda `#5c6570`)
    - **Trabalhando:** escreveu nos últimos 90 segundos (ponto `#16a34a`)
- **Direita — criador** (`padding-left:16px; border-left:1px solid rgba(255,255,255,.12); gap:10px`):
  - Avatar circular 34px, `background: linear-gradient(135deg,#5b7cff,#a78bfa)`, texto "EA" 12.5px peso 700 branco.
  - Coluna: "CRIADO POR" (10px, 700, uppercase, `letter-spacing:.08em`, `#7088a6`) e link "Erick Álvaro da Silva" (13px, 600, `#fff`, nowrap) → `https://www.linkedin.com/in/erick-silva/` (`target=_blank rel="noopener noreferrer"`).
  - Botão LinkedIn 30×30, `border-radius:8px`, fundo `rgba(112,181,249,.14)` (hover `.26`), ícone 15px `#70b5f9`, mesmo `title`/`aria-label` de hoje.
- O `<meta name="author">` e a menção "TekLabs Digital" continuam.

### Conteúdo
- `main`: `max-width:1240px; margin:0 auto; padding:28px 32px 56px; display:flex; flex-direction:column; gap:22px`.
- `body` fundo `#f4f6f9` (antes `#f6f7f9`).
- Avisos (`.aviso`) continuam no topo do `main`, mesmo estilo.
- Rodapé "Atualiza sozinho a cada 5 segundos…" fica no fim da tela de lista (12px `#5c6570`).

---

## Tela 1 — Lista de projetos (`#/`)

### Cabeçalho da página
`display:flex; justify-content:space-between; align-items:flex-end; gap:20px; flex-wrap:wrap`.
- Esquerda: `h1` "Painel dos times de agentes" (26px, 700, `line-height:1.2`, `letter-spacing:-.01em`). Abaixo, `dados.workspace` em monospace (`ui-monospace, Consolas, monospace`) 12.5px `#5c6570`, `margin-top:6px`, uma linha com reticências.
- Direita: faixa de 3 números num cartão (`background:#fff; border:1px solid #e2e5ea; border-radius:12px; overflow:hidden`), cada célula `padding:10px 18px`, separador `1px solid #eef0f3`. Número 22px peso 600 `tabular-nums`, rótulo 12px `#5c6570` nowrap:
  - **trabalhando** (cor `#15803d`): projetos cujo time escolhido está `trabalhando`;
  - **agentes ativos agora**: soma de `t.medido.trabalhando` dos times exibidos;
  - **sem atividade** (cor `#5c6570`): projetos sem time nos últimos 7 dias.

### Filtro + busca (novo; estado só no cliente)
- Segmentado: fundo `#e9ecf1`, `border-radius:10px`, `padding:3px`, `gap:2px`. Botões 13px `padding:6px 14px; border-radius:8px`; o ativo tem fundo `#fff`, cor `#1b1f24`, peso 600, `box-shadow:0 1px 2px rgba(11,31,58,.12)`; os inativos são transparentes, `#5c6570`. Opções com contagem em `opacity:.6`: **Todos N** · **Com time N** · **Sem atividade N**.
- Busca: `flex:0 1 280px`, `background:#fff; border:1px solid #e2e5ea; border-radius:10px; padding:7px 12px`, ícone de lupa 14px `#8a939e`, placeholder "Buscar projeto"; foco `border-color:#2563eb`. Filtra por nome (sem diferenciar maiúsculas). Sem resultado: caixa tracejada "Nenhum projeto com esse nome." (`border:1px dashed #d4d8de; border-radius:12px; padding:28px; text-align:center`).
- Guarde filtro e busca em variáveis do módulo. **Importante:** como `desenhar()` refaz o `innerHTML` a cada 5 s, o campo de busca não pode perder foco nem texto — renderize a barra de filtros uma única vez fora de `#conteudo` (ou restaure foco e seleção depois de cada `desenhar()`).

### Cartões de projetos com time
Grade: `display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr)); gap:16px`. A ordem continua a de `dados.projetos`.

Cartão (`<a href="#/projeto/…">`): `background:#fff; border:1px solid #e2e5ea; border-radius:14px; padding:20px; display:flex; flex-direction:column; gap:14px; box-shadow:0 1px 2px rgba(11,31,58,.04); transition: border-color .15s, box-shadow .15s`. Hover: `border-color:#9db8f5; box-shadow:0 8px 24px rgba(11,31,58,.08)`, sem sublinhado.
1. **Topo**: nome (17px, 700) + subtítulo 13px `#5c6570` (`<nome do time> · última escrita há …`). À direita, o selo da situação (com ponto pulsante quando `trabalhando`).
2. **Plano** (se houver plano `em andamento`): caixa `background:#f1f3f6; border-radius:10px; padding:12px 14px; gap:8px`.
   - Rótulo "PLANO · INFORMADO PELO GERENTE" (11px, 700, uppercase, `letter-spacing:.06em`, `#5c6570`).
   - Demanda 14px `line-height:1.4`.
   - **Barra segmentada**: um segmento por fase (`flex:1; height:5px; border-radius:3px; gap:4px`): aprovada `#15803d`, em andamento ou em QA `#2563eb`, pendente `#e2e5ea`.
   - Linha 12.5px `#5c6570`: "`N` de `T` fases aprovadas pelo QA · agora: `<onde>`".
3. **Gerente**: "Gerente" `#5c6570` + selo pequeno (12px, `padding:1px 8px`) + "sessão X · última escrita na conversa há …" 12px `#5c6570`; adicione `g.motivo` em negrito se existir.
4. **Medido**: `border-top:1px solid #eef0f3; padding-top:12px; gap:8px`. Rótulo "MEDIDO" `#2563eb`. Números lado a lado (`gap:22px`): valor 20px 600 `tabular-nums`, rótulo 12px `#5c6570`. Mesmos itens de `blocoMedido(t, true)` (lançados ou iniciados, "já começaram", encerrados, trabalhando agora em `#15803d` quando > 0, repetidos, falharam). Barra 6px (`#e5e8ec`, preenchimento `#2563eb`) = encerrados / lançados.
5. **Estimativa** (só se não houver plano e `e.base`): `background:#f7f4fe; border:1px dashed #a78bfa; border-radius:10px; padding:10px 12px`. Linha: "ESTIMATIVA" `#7c3aed` · **`P`% concluído** · `faltam cerca de …` · `cerca de N agentes no total` (`#5c6570`). Barra 6px fundo `#ebe5fb`, preenchimento `repeating-linear-gradient(135deg,#7c3aed 0 5px,#b99cf2 5px 10px)`. A nota longa ("É uma estimativa…") sai do cartão e fica só no detalhe.
6. **Rodapé**: à esquerda "mais N times nos últimos 7 dias" (12.5px `#5c6570`); à direita "Abrir projeto →" (`#2563eb`, 600).

### Projetos sem atividade (grade compacta)
- Título `h2` "Sem atividade" 15px + "nenhum time nos últimos 7 dias" 13px `#5c6570`.
- Grade `repeat(auto-fill,minmax(200px,1fr)); gap:8px`. Item (link): `background:#fafbfc; border:1px solid #e8ebef; border-radius:10px; padding:10px 14px`. Nome 14px 600 `#3a424c` com reticências; abaixo "nenhum time ainda" ou "nenhum time nos últimos 7 dias" (12px `#7a838e`). Hover: fundo `#fff`, borda `#c9d3e0`.
- Projetos só com plano (sem time) continuam como cartão grande.
- "Sem projeto identificado" entra nesta grade quando não tem time; se tiver time ou plano, vira cartão grande, com o subtítulo "N times e N planos fora das pastas da workspace".

---

## Tela 2 — Detalhe do projeto (`#/projeto/<nome>`)

1. **Trocador de projetos** (substitui o link `.voltar`): linha `display:flex; gap:8px; overflow-x:auto`.
   - Primeira pílula: "← Todos os projetos".
   - Depois, uma pílula por projeto com time: ponto 7px na cor da situação + nome.
   - Pílula normal: `border:1px solid #e2e5ea; background:#fff; border-radius:999px; padding:5px 12px; font-size:13px`.
   - Projeto atual: fundo e borda `#0b1f3a`, texto branco, peso 600. Hover: `border-color:#2563eb`.
   - Cor dos pontos: trabalhando `#16a34a`, aguardando `#f59e0b`, em andamento ou ocupado `#2563eb`, demais `#94a3b8`.
2. **Título**: `h1` 28px 700 + selo da situação do time principal; abaixo, linha 13px `#5c6570`: "N times nos últimos 7 dias · última escrita há …".
3. **Alerta** (quando algum gerente está `aguardando`): `background:#fef3c7; color:#92400e; border-radius:10px; padding:12px 16px; font-size:14px`, com ícone de alerta 18px: "O gerente parou esperando você aprovar uma ação no Claude Code. O time não avança até você responder."
4. **Plano** (`blocoPlano`): cartão `#fff`, `border:1px solid #e2e5ea; border-radius:14px; padding:20px 22px; gap:16px`.
   - Topo: rótulo "PLANO · INFORMADO PELO GERENTE"; `h2` com a demanda (18px, `line-height:1.35`); linha "Criado … · atualizado … · arquivo" (12.5px). À direita: "**3** / 4" (24px; o "/ 4" em `#a0a8b2` peso 400) + "fases aprovadas pelo QA".
   - **Fases em colunas**: `grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px`. Cada fase tem `border-top:3px solid <cor>` e `padding-top:10px`, com três linhas:
     - código em negrito na cor da fase + título 14px 600;
     - situação 12.5px na cor da fase ("✓ aprovada", "em QA", "em andamento", "pendente");
     - "N agentes · QA <situação>" 12px `#5c6570`.
     Cores: aprovada `#15803d`; em andamento ou em QA `#2563eb`; pendente: barra `#e2e5ea`, texto `#5c6570`. Subfases, tokens e QA detalhado vão numa linha 12px abaixo da coluna, com o mesmo texto de hoje.
   - Faixa de estimativa: `background:#f7f4fe; border:1px dashed #a78bfa; border-radius:8px; padding:9px 12px`: "ESTIMATIVA" + texto atual.
   - Mantenha a nota "Nenhum agente com o código da fase…" quando `!p.agentes_ligados`.
5. **Cartão de time** (um por time): `background:#fff; border:1px solid #e2e5ea; border-radius:14px; overflow:hidden`.
   - **Cabeça** (`padding:18px 22px 16px; border-bottom:1px solid #eef0f3; gap:6px`):
     - `h2` 18px + selo + etiqueta do tipo;
     - linha "Começou … · última escrita … · Projeto identificado por …" 12.5px;
     - linha do Gerente (mesma do cartão);
     - notas `semRoteiro` e `naoConfirmado` como estão hoje.
   - **Faixa de 3 blocos**: `grid-template-columns:repeat(auto-fit,minmax(250px,1fr))`, cada bloco `padding:16px 22px`, divisória `1px solid #eef0f3`.
     - **Medido**: rótulo `#2563eb`, números 22px, barra 6px, "rodando há …" 12px. A nota "N de N agentes já iniciados terminaram…" fica abaixo da barra, 12px.
     - **Estimativa**: fundo `#fbf9ff`, rótulo `#7c3aed`, título 20px "`P`% · faltam cerca de …" (ou "Sem base para estimar"), barra tracejada e nota explicativa 12px (texto atual de `blocoEstimativa`).
     - **Tokens (equiv.)**: rótulo `#5c6570`, números 22px "agentes" e "conversa do gerente". Para Codex, inclua os tokens do Codex e dos subagentes. Mantenha os `title` com o detalhe.
   - **Fases (medido)** se `t.fases.length`: faixa `padding:14px 22px`, rótulo "FASES" `#2563eb`, pílulas iguais às de hoje (`.fase.feita/.atual/.futura`).
   - **Tabela de agentes** sem margem extra, ocupando a largura do cartão:
     - cabeçalho com fundo `#fafbfc`, 12px `#5c6570` 600, `padding:9px 10px`, primeira e última coluna com 22px nas laterais;
     - linhas 13.5px, `border-bottom:1px solid #eef0f3`, hover `#fafbfc`; colunas numéricas alinhadas à direita com `tabular-nums`.
     Mesmas colunas e regras de hoje (coluna Fase condicional).
6. Sem times: caixa tracejada "Nenhum time trabalhou neste projeto nos últimos 7 dias."

---

## Interações e comportamento
- As rotas por hash continuam. Ao trocar de rota: `window.scrollTo(0,0)` (já existe).
- Legenda: alterna no botão; fecha com clique fora ou `Escape`.
- Filtro e busca: só no cliente, sobrevivem ao refresh de 5 s (veja a nota acima).
- Pulso: o `@keyframes pulso` e o `prefers-reduced-motion` atuais continuam.
- Hover dos cartões: transição de 150 ms em borda e sombra.
- Largura estreita (< 720px): o cabeçalho quebra em linhas (`flex-wrap`), a faixa de números vai para baixo do título, e os cartões e blocos caem para 1 coluna pelos `auto-fit`. O bloco do criador pode esconder o rótulo "Criado por" abaixo de 560px.
- **Modo escuro**: o arquivo atual tem `@media (prefers-color-scheme: dark)`. O cabeçalho já é escuro nos dois modos. Para o conteúdo, mapeie os novos valores para as variáveis existentes (ex.: `#f4f6f9 → --fundo`, `#fff → --cartao`, `#eef0f3 → --linha` suave, `#f1f3f6 → --neutro-fundo`, `#f7f4fe/#fbf9ff → --estimado-fundo`) e crie as que faltarem (`--cabecalho: #0b1f3a`, `--linha-suave`). Não deixe hex fixos no conteúdo.

## Estado (JS)
Além do que já existe (`dados`, `erro`, `erroConexao`, `ultimaCarga`):
- `filtro` = `"todos" | "ativos" | "inativos"`
- `busca` = string
- `legendaAberta` = boolean

Nenhuma mudança em `/api/estado`.

## Tokens de design
| Uso | Valor |
|---|---|
| Cabeçalho | `#0b1f3a`; texto `#dbe4f0`; secundário `#8fa3bd`; rótulos `#7088a6`; bordas `rgba(255,255,255,.12–.16)` |
| Fundo da página | `#f4f6f9` |
| Cartão | `#fff`, borda `#e2e5ea`, divisória interna `#eef0f3`, raio 14px |
| Texto | `#1b1f24`; suave `#5c6570`; terciário `#a0a8b2` |
| Destaque / Medido | `#2563eb` (hover de cartão `#9db8f5`) |
| Estimativa | `#7c3aed`, borda `#a78bfa`, fundos `#f7f4fe` / `#fbf9ff` / `#ebe5fb`, listra `#b99cf2` |
| Plano (informado) | `#f1f3f6` |
| OK / trabalhando | `#15803d` sobre `#dcfce7`; ponto `#16a34a` (claro) / `#4ade80` (no cabeçalho) |
| Alerta | `#b45309` sobre `#fef3c7`; texto do banner `#92400e` |
| Erro | `#b91c1c` sobre `#fee2e2` |
| Marca (degradê) | `#5b7cff → #a78bfa`; ciano `#22d3ee` |
| Raios | 999px (pílulas), 14px (cartões), 12px (popover, faixa de números), 10px (caixas internas, ícone), 8px (botões pequenos), 3px (barras) |
| Sombras | cartão `0 1px 2px rgba(11,31,58,.04)`; hover `0 8px 24px rgba(11,31,58,.08)`; popover `0 14px 36px rgba(11,31,58,.22)` |
| Tipografia | 28/26px h1 · 18px h2 · 17px nome do cartão · 22/20px números · 15px base · 13–13.5px corpo · 12px notas · 11px rótulos uppercase 700 `.06em` |
| Espaços | gutter 32px · gap da página 22px · gap da grade 16px · padding de cartão 20px / 22px |

## Assets
- `assets/icone-rede.svg` — **novo ícone do painel** (40×40, para o cabeçalho). Copie para `monitor/icons/icone-rede.svg`.
- `assets/icone-rede-pwa.svg` — mesma marca no formato do `icone.svg` (100×100, fundo `#0b1f3a`, rx 22). Para a nova marca valer também no PWA, substitua `monitor/icons/icone.svg` e rode `tools/gerar_icones.py` para gerar de novo `icone-192.png`, `icone-512.png` e `icone-maskable-512.png`.
- `logo-teklabs.svg` — já existe em `monitor/icons/`; só muda o tamanho (47×17).
- Os ícones de lupa, interrogação, alerta e LinkedIn são SVG inline (veja a referência).

## Arquivos neste pacote
- `README.md` — este documento.
- `PROMPT-claude-code.md` — prompt pronto para colar no Claude Code.
- `assets/icone-rede.svg`, `assets/icone-rede-pwa.svg` — nova marca.
- `referencia/Painel de Agentes v2.dc.html` (+ `support.js`, `assets/`) — protótipo navegável com dados fictícios (clique nos cartões para ver o detalhe).
