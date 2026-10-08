Cole o texto abaixo no Claude Code, aberto na raiz do repositório `teklabs-painel-agentes`, depois de copiar esta pasta para `docs/design_handoff_painel_layout_v2/`.

---

Implemente a atualização de layout descrita em `docs/design_handoff_painel_layout_v2/README.md` no arquivo `monitor/index.html`.

Regras:
- Mude só a apresentação: a casca (cabeçalho com a marca do painel, o criador, o status e a legenda), a tela de lista e a tela de detalhe do projeto. **Sem barra lateral.**
- Não altere `painel.py`, o contrato de `/api/estado`, as regras de situação, os cálculos nem os textos explicativos. Os textos já existentes ficam iguais, palavra por palavra.
- Mantenha a arquitetura atual: um HTML único, CSS com variáveis em `:root` (incluindo o modo escuro em `prefers-color-scheme`), JS puro com `innerHTML`, rotas por hash. Sem framework, sem build, sem dependências.
- Use a referência navegável em `docs/design_handoff_painel_layout_v2/referencia/Painel de Agentes v2.dc.html` (sirva por HTTP) para conferir o visual. Os valores exatos estão no README.
- Copie `assets/icone-rede.svg` para `monitor/icons/` e use no cabeçalho. Substitua `monitor/icons/icone.svg` por `assets/icone-rede-pwa.svg` e rode `tools/gerar_icones.py` para gerar os PNGs do PWA. Se o `sw.js` tiver lista de cache versionada, aumente a versão.
- O campo de busca não pode perder foco nem texto no refresh automático de 5 s.

Ao terminar:
1. Rode `python monitor/painel.py` e confira `http://127.0.0.1:8765/` na lista e no detalhe de um projeto com plano e de outro com time trabalhando, em modo claro e escuro e com a janela estreita (~700px).
2. Atualize a seção "Telas" do `monitor/README.md` se a descrição mudar (filtro, busca, trocador de projetos, legenda no cabeçalho).
3. Mostre um resumo do diff.
