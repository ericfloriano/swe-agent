# SWE Local Agent

Plataforma local de desenvolvimento SWE offline. O sistema simula um fluxo enxuto de planejamento, aprovacao humana e desenvolvimento de software, usando modelos locais via Ollama, com foco em privacidade, observabilidade e execucao local aceleravel por CPU ou GPU integrada quando o ambiente do Ollama permitir.

## Current State

Data de referencia: 2026-07-13.

O fluxo ativo da GUI e sempre:

1. usuario envia um pedido de desenvolvimento;
2. **Planner Agent** gera ou ajusta `implementation_plan.md`;
3. usuario aprova ou pede ajuste do plano;
4. **Developer Agent** escreve os arquivos e conclui a codificação;
5. frontend mostra arquivos, logs, timer, metricas, rodape de hardware/LLM e mensagem final.

O perfil de execucao rapido direto foi removido da interface e do caminho ativo do backend. O editor manual tambem foi removido da GUI. A coluna central deve focar em `Visualizador` e `Logs de Execucao`.

O ambiente testado agora possui aceleracao Ollama por GPU integrada AMD Radeon Vega 8 via Vulkan. A solucao nao instala driver, nao faz overclock e nao altera hardware; ela apenas permite selecionar modelos locais, executa chamadas via Ollama e registra passivamente CPU, RAM, temperatura, GPU, memoria compartilhada e modelos carregados.

O sweet spot atual observado nos benchmarks e:

* Planner: `qwen2.5-coder-1.5b-qa:latest`
* Developer: `qwen2.5-coder-7b-local:latest`
* Runtime: Ollama com `OLLAMA_VULKAN=1`, `GGML_VK_VISIBLE_DEVICES=0` e `OLLAMA_IGPU_ENABLE=1` no servico do Ollama

A GUI continua permitindo testar outros modelos listados pelo Ollama. O projeto deve ser tratado como uma bancada de comparacao local, nao como uma configuracao fixa e fechada.

## Language

**Workspace**:
Diretorio fisico isolado em `workspaces/<project_id>` onde o codigo gerado e armazenado, versionado via Git local e exibido no frontend.
_Avoid_: sandbox generico, pasta temporaria, projeto global

**State Memory Tracker**:
Arquivo `.swe_local_agent/state.json` dentro do workspace. Persiste prompt, plano, etapa atual, arquivos criados, logs, metricas, timer de execucao, runtime visual, snapshots de hardware e evidencias silenciosas de qualidade.
_Avoid_: cache de chat, memoria informal, log solto

**Runtime Snapshot**:
Campo `runtime` no `state.json` usado para recuperar status, preview rolante e atividade do agente quando o SSE oscila, o frontend recarrega ou o usuario clica em arquivos durante uma execucao.
_Avoid_: estado definitivo do workflow

**Hardware Snapshot**:
Entrada em `hardware_snapshots` no `state.json` gravada em momentos-chave, como inicio/fim do Planner e inicio/fim do Developer. Registra CPU, RAM, temperatura, GPU AMD detectada, memoria VRAM/GTT e status do Ollama.
_Avoid_: benchmark externo, telemetry invasiva, alteracao de driver

**Ollama Runtime Snapshot**:
Subcampo do Hardware Snapshot que descreve `processor`, modelos carregados, memoria reportada e se a memoria alvo e CPU, GPU dedicada ou GPU integrada com memoria compartilhada.
_Avoid_: suposicao manual, chute de VRAM

**Quality Evidence**:
Campo `quality_checks` no `state.json`. Guarda sinais de aderencia ao escopo, arquivos planejados vs. criados, desvio de dominio e avisos. No estado atual, nao aparece como Quality Check na UI e nao bloqueia o Planner; serve como evidencia para analise posterior.
_Avoid_: gate bloqueante, score visual obrigatorio, QA Agent separado

**Execution Timer**:
Campo `execution_timer` no `state.json`. Soma apenas tempo ativo do Planner e do Developer. Pausa apos entrega do plano e retoma quando o usuario aprova/codifica ou ajusta o plano.
_Avoid_: tempo de parede total, tempo de sessao Streamlit

**Planner Agent**:
Agente que cria e revisa `implementation_plan.md`. Ele descreve arquitetura, arquivos esperados e criterios de aceite.
_Avoid_: agente desenvolvedor, gerador de arquivos, PM Agent

**Planner Boundary**:
Regra que impede o Planner Agent de escrever codigo-fonte, blocos `[FILE:]`, pseudocodigo executavel ou conteudo final de arquivos. O backend aplica sanitizacao defensiva caso o modelo quebre essa regra.
_Avoid_: implementacao antecipada, codigo no plano

**Developer Agent**:
Agente que le o plano aprovado e escreve os arquivos fisicos usando blocos `[FILE:]` de forma direta e concisa.
_Avoid_: QA Agent, Planner, executor de testes externo

**Developer Execution**:
Escrita direta e concisa do código no workspace, focada no plano de implementação aprovado.
_Avoid_: suite de validação redundante, explicações ou conversas longas antes/depois do código

**Offline Model Profile**:
Combinacao de modelos escolhida para Planner e Developer, por exemplo `qwen2.5-coder-1.5b-qa:latest -> qwen2.5-coder-7b-local:latest`. Perfis devem ser comparados por `metrics`, `execution_timer`, `files_created`, `hardware_snapshots` e `quality_checks`.
_Avoid_: modelo unico fixo, decisao por percepcao sem benchmark

**Structured File Block**:
Formato esperado para escrita de arquivo:

````text
[FILE: caminho/do/arquivo.ext]
```linguagem
conteudo
```
````

O parser aceita variantes comuns como fallback, mas o prompt do Developer deve continuar exigindo `[FILE:]`.
_Avoid_: salvar codigo em `.txt`, nome do arquivo apenas como comentario

**Development Prompt**:
Mensagem do usuario que pede criacao, correcao, refatoracao ou documentacao de software. Deve iniciar o fluxo Planner -> aprovacao -> Developer.
_Avoid_: pergunta casual

**Conversational Prompt**:
Mensagem do usuario que busca explicacao, status ou orientacao sem alterar arquivos. Hoje ainda nao ha roteamento natural na GUI; uma evolucao futura e adicionar modo `Conversar` / `Desenvolver` ou Intent Router leve.
_Avoid_: nova tarefa de desenvolvimento

**Intent Router**:
Evolucao planejada, ainda nao implementada. Deve classificar mensagens entre conversa, ajuste de plano e nova tarefa de desenvolvimento antes de acionar o Planner.
_Avoid_: terceiro agente pesado sempre ativo

**Backend Orchestrator**:
Servico FastAPI em `app_backend/main.py` que executa o LangGraph, gerencia tarefas assicronas, SSE, stop, estado e metricas.
_Avoid_: frontend, Streamlit, cliente Ollama

**Frontend GUI**:
Interface Streamlit em `app_gui/main.py`. Renderiza workspace, arquivos, visualizador, logs, chat, spinner, botao de interrupcao, rodape e timer.
_Avoid_: backend, CLI, orquestrador

**Reasoning Stream**:
Tokens dentro de `<think>...</think>` capturados do Ollama e renderizados separadamente quando o modelo os fornece.
_Avoid_: log de execucao, resposta final do agente

**Execution Log**:
Lista organizada no frontend a partir de `log_messages`, `metrics`, `files_created` e `execution_timer`. Serve para auditoria da execucao.
_Avoid_: console bruto, stdout do processo

**LLM Footer**:
Indicador no rodape da GUI que resume o estado do Ollama, por exemplo `LLM: GPU 6.1 GB comp. (2)`. `GPU` vem do Ollama, `comp.` significa memoria compartilhada e `(2)` indica modelos carregados.
_Avoid_: diagnostico completo de driver, promessa de VRAM dedicada

## Example Dialogue

**Developer**: "O **Planner Agent** salvou `implementation_plan.md`. O usuario deve revisar o arquivo no **Workspace** e aprovar antes do **Developer Agent** escrever arquivos."

**Domain Expert**: "Correto. Mantenha o **Planner Boundary**, registre metricas e **Hardware Snapshot** no **State Memory Tracker**, atualize o **Execution Timer** por fase e use **Structured File Blocks** para que o frontend consiga listar os arquivos conforme forem escritos."
