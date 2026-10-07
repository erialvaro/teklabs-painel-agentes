#!/usr/bin/env bash
# Instalador do Painel de Agentes · TekLabs Digital (macOS e Linux)
# Criado por Erick Álvaro da Silva · TekLabs Digital
# Uso: bash install.sh [opções do instalar.py]
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PYTHON="$(command -v "$c")"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Python 3.9 ou mais novo não foi encontrado."
  case "$(uname -s)" in
    Darwin) echo "Instale com:  brew install python   (ou pelo site python.org) e rode de novo." ;;
    *)      echo "Instale com o gerenciador do sistema, por exemplo:  sudo apt install python3   e rode de novo." ;;
  esac
  exit 1
fi

echo "Usando Python: $PYTHON"
exec "$PYTHON" "$RAIZ/instalar.py" "$@"
