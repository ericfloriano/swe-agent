# SWE Local Agent CLI Demo

Este modo e a forma mais simples de demonstrar o desafio: um CLI local com agentes usando modelos offline via Ollama.

A CLI aceita qualquer modelo registrado no Ollama. Isso permite comparar perfis diferentes sem alterar codigo.

## Fluxo

1. Planner Agent: usa um modelo de reasoning para gerar `implementation_plan.md`.
2. Developer Agent: usa um modelo coder para escrever os arquivos no workspace de forma direta e concisa.

Nao ha chamada externa. Os arquivos ficam em `workspaces/<nome-do-projeto>/`.
O CLI usa o mesmo cliente Ollama do backend, entao respeita `OLLAMA_KEEP_ALIVE`, `OLLAMA_USE_MMAP` e o padrao `keep_alive="30m"`.

## Exemplo

```bash
source venv/bin/activate

python -m app_cli.main \
  --workspace estoque_cli \
  --planner-model qwen2.5-coder-1.5b-qa:latest \
  --developer-model qwen2.5-coder-7b-local:latest \
  --auto-approve \
  --prompt "Crie uma API Node.js Express com POST /produtos e GET /produtos. Valide preco maior que zero e quantidade_estoque nao negativa."
```

Para mostrar o reasoning quando o modelo emitir tags `<think>`:

```bash
python -m app_cli.main \
  --workspace estoque_cli_reasoning \
  --auto-approve \
  --show-thinking \
  --prompt "Crie uma API Node.js Express simples para estoque de camisetas infantis."
```

## Pontos para apresentar

- O Planner cria o plano antes do codigo.
- O Developer escreve os arquivos de código diretamente com commits Git locais correspondentes.
- O sandbox impede escrita fora de `workspaces/<projeto>`.
- O Git local permite auditar cada etapa.
- O `keep_alive` reduz recarregamento de modelo entre Planner e Developer; o cliente usa `use_mmap=true` por padrao.
- O perfil recomendado nos benchmarks recentes usa `qwen2.5-coder-1.5b-qa:latest` como Planner e `qwen2.5-coder-7b-local:latest` como Developer.
- Outros modelos testados incluem `llama3.2-3b-planner:latest`, `llama3.2-3b-local`, `qwen2.5-coder-3b-developer:latest` e `qwen2.5-coder-3b-local`.
- Quando o Ollama esta acelerado por GPU/Vulkan, o `state.json` e o endpoint `/api/system/metrics` ajudam a comprovar se a execucao ocorreu em CPU, GPU ou modo misto.
