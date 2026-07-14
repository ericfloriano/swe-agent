# API REST Nativa do Ollama para Extração de Raciocínio (Thinking)

Decidimos utilizar a API REST nativa do Ollama, principalmente o endpoint `/api/generate`, para comunicação direta com os modelos locais, em vez de depender de classes abstratas do LangChain como `ChatOllama`.

Essa decisão permite:

* ler streaming bruto de tokens;
* interceptar tags `<think>` e `</think>` em tempo real;
* separar Reasoning Stream da resposta final no frontend;
* capturar métricas como `prompt_eval_count`, `eval_count`, durações e TPS;
* controlar parâmetros de performance como `keep_alive`, `use_mmap` e override opcional de threads.

O `keep_alive` padrão do cliente é `30m`, com override por `OLLAMA_KEEP_ALIVE`. Essa configuração reduz recarregamentos entre Planner e Developer sem prender RAM indefinidamente como ocorreria com `-1`. O cliente envia `options.use_mmap=true` por padrão, com override por `OLLAMA_USE_MMAP=false` quando for necessário diagnosticar comportamento do runtime.

Os parâmetros estáveis de geração ficam preferencialmente nos `Modelfile`s do Ollama. O cliente não força mais `num_thread` em toda chamada; quando necessário, use `OLLAMA_NUM_THREAD=4`, `6` ou `8` para comparar desempenho sem recriar modelos. Para o workflow padrão em CPU, o orquestrador envia limites explícitos mais econômicos: Planner com `num_ctx=2048` e `num_predict=512`; Developer com `num_ctx=4096` e `num_predict=1400`. O backend não agenda Fast Start no startup por padrão; `SWE_AGENT_FAST_START=1` habilita esse comportamento quando a máquina é dedicada ou quando a latência inicial importa mais que memória livre. A GUI não chama Fast Start ao renderizar ou selecionar modelos; ela só chama `/api/system/fast-start` quando o usuário aciona explicitamente **Preparar modelos**. A GUI atual usa o fluxo completo com Planner, aprovação humana e Developer, preservando os parâmetros do modelo para manter previsibilidade e rastreabilidade.
