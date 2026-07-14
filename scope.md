# **Software Requirements Specification (SRS) & PRD**

## **Projeto: SWE Local Agent (Plataforma Agêntica de Desenvolvimento SWE Offline)**

Este documento define o escopo, arquitetura técnica, fluxo de agentes, engenharia de prompts e especificações de interface para o desenvolvimento da plataforma de engenharia de software agêntica offline **SWE Local Agent**, otimizada para o hardware Lenovo IdeaPad S145, com compatibilidade garantida para Linux Mint e Windows.

## **1\. Visão Geral do Sistema e Restrições de Hardware**

O **SWE Local Agent** é uma IDE agêntica de desenvolvimento de software local projetada para simular um fluxo enxuto de engenharia de software, automatizando planejamento e desenvolvimento com total privacidade (100% offline).

**Escopo atual do MVP:** o sistema opera com **2 agentes LLM locais** em fluxo sequencial com aprovação humana:

1. **Planner Agent:** cria e revisa o `implementation_plan.md`.
2. **Developer Agent:** gera os arquivos físicos diretamente de forma concisa e limpa.

Agentes adicionais de QA, DOM ou segurança ficam fora do workflow padrão para reduzir latência, consumo de contexto e custo de inferência local.

Na GUI, toda nova solicitação de desenvolvimento deve gerar ou revisar um `implementation_plan.md` antes da codificação. O usuário revisa o plano no painel de arquivos e escolhe entre aprovar a codificação ou enviar feedback para ajustar o plano. O modo rápido direto foi removido do caminho ativo para manter previsibilidade acadêmica, rastreabilidade e equivalência com fluxos como Codex, Claude Code e Antigravity.

### **Perfil de Hardware Alvo (Lenovo IdeaPad S145)**

A arquitetura do sistema foi projetada sob medida para as especificações físicas do ambiente local do usuário:

* **Sistema Operacional Primário:** Linux Mint 22.3 Zena (Kernel 6.8.0-generic, Cinnamon Desktop).  
* **Compatibilidade Obrigatória:** Windows 10/11 (utilizando abstrações multiplataforma).  
* **Processador (CPU):** AMD Ryzen 5 3500U (4 núcleos físicos, 8 threads, cache L2 de 2 MiB, arquitetura Zen+).  
* **Placa de Vídeo (GPU):** AMD Radeon Vega 8 (Integrada, compartilhando largura de banda de memória RAM DDR4).  
* **Memória RAM:** **20 GB DDR4** (Disponibilidade real média de \~17.4 GB livre).  
* **Armazenamento:** SSD NVMe Kingston SNV2S500G de 500GB (ext4 no Linux).

### **Premissas Críticas de Execução Local**

1. **Execução Local com Baseline CPU e Perfil GPU Validado:** CPU continua sendo o baseline seguro e portável, mas o ambiente Lenovo IdeaPad S145 foi validado com Ollama usando a GPU integrada AMD Radeon Vega 8 via Vulkan. A GPU é integrada e usa memória compartilhada com a RAM; portanto, o sistema registra o comportamento real em `hardware_snapshots` em vez de assumir VRAM dedicada.  
2. **Controle de CPU Threads:** O cliente respeita os parametros do Modelfile/Ollama e aceita override por `OLLAMA_NUM_THREAD`, permitindo comparar 4, 6 ou 8 threads sem recriar modelos.  
3. **Aproveitamento de RAM (20 GB):** A ampla capacidade de memória permite manter até dois modelos úteis ao MVP (Planner e Developer) carregados por mais tempo. As chamadas HTTP locais usam `keep_alive="30m"` e `use_mmap=true` por padrão, configuráveis via `OLLAMA_KEEP_ALIVE` e `OLLAMA_USE_MMAP`.

## **2\. Arquitetura de Multi-Modelos GGUF Locais**

A plataforma divide as demandas cognitivas entre dois modelos locais para manter o sistema responsivo no hardware do laptop. O projeto não é preso a uma dupla fixa: a GUI lista os modelos do Ollama e permite testar combinações diferentes para Planner e Developer.

                         \+-------------------------+  
                         | OLLAMA local CPU/GPU     |  
                         | CPU baseline / Vulkan iGPU|  
                         \+------------+------------+  
                                   |  
        \+--------------------------+  
        |                          |  
\+-------v-------+          \+-------v-------+  
| Planner local |          | Developer     |  
| leve/rapido   |          | coder local   |  
\+-------+-------+          \+-------+-------+  
| Planner Agent |          | Developer     |  
| Plano leve    |          | Código/Check  |  
\+---------------+          \+---------------+

### **Configuração de Papéis por Modelo**

| Modelo Disponível no Disco/Ollama | Tamanho Estimado | Papel Atribuído | Justificativa de Engenharia |
| :---- | :---- | :---- | :---- |
| **qwen2.5-coder-1.5b-qa:latest** | \~1.6 GB carregado | **Planner recomendado nos benchmarks recentes** | Melhor equilíbrio observado para planejar rápido sem alongar demais a etapa. |
| **qwen2.5-coder-7b-local:latest** | \~4.4 GB carregado | **Developer recomendado nos benchmarks recentes** | Modelo coder mais forte testado no projeto; tornou-se viável após aceleração via Vulkan/iGPU. |
| **Qwen2.5-Coder-3B-Instruct-Q4_K_M / qwen2.5-coder-3b-developer:latest** | \~2.2 GB | **Alternativa rápida** | Pode substituir Planner ou Developer em tarefas pequenas quando a prioridade for velocidade e previsibilidade de demonstração. |
| **Llama-3.2-3B-Instruct-Q4_K_M / llama3.2-3b-planner:latest** | \~2.0 GB | **Planner alternativo testado** | Funcionou como Planner, mas no `app_task_5` foi mais lento que o Qwen 1.5B no benchmark de atividades. |

## **3\. Orquestração da Equipe de Agentes (Framework Pipeline)**

A orquestração do pipeline de agentes será construída utilizando um framework de grafo de estados (sugestão: **LangGraph** para controle estrito de loops e condicionais, ou **CrewAI** estruturado com tarefas sequenciais).

\[Início: Prompt\] \---\> (Planner Agent) \---\> \[Gera implementation\_plan.md\]  
                             ^                         |  
                             |                   (Aprovação?)  
                             |                         |  
                      \[User Feedback\] \<----------- No / Yes  
                                                       |  
                                                       v  
                                               (Developer Agent)  
                                                       |  
                                                       v  
                                                \[Gera Arquivos\]  
                                                       |  
                                                       v  
                                                \[Entrega Final\]

### **3.1. Papéis e Atribuições Detalhadas da Equipe Agêntica**

1. **Planner Agent:**  
   * **Atribuição:** Interage inicialmente com o usuário. Traduz a solicitação em linguagem natural em um arquivo `implementation_plan.md` modularizado, com arquitetura, arquivos previstos e critérios de aceite. O Planner não deve escrever código-fonte, blocos `[FILE:]`, conteúdo final de README ou arquivos finais; isso pertence ao Developer Agent.  
2. **Developer Agent:**  
   * **Atribuição:** Escreve os arquivos funcionais com base no plano aprovado de forma direta e concisa, sem explicações redundantes ou conversações fora dos blocos de código.

## **4\. Fluxo de Trabalho Agêntico e Estado de Memória**

### **4.1. Loop de Planejamento Interativo com Memória**

O sistema mantém um estado persistente estruturado em formato JSON (State Memory Tracker) para garantir que o contexto histórico não se perca durante as revisões de plano de implementação feitas pelo usuário:

{  
  "project\_id": "unique-uuid",  
  "original\_prompt": "Prompt inicial digitado pelo usuário",  
  "current\_version": "2.0",  
  "history": \[  
    {  
      "version": "1.0",  
      "plan\_content": "...markdown...",  
      "user\_feedback": "Adicione um botão para limpar a lista"  
    }  
  \]  
}

* **Comportamento Iterativo:** Ao receber feedback do usuário, o **Planner Agent** analisa o histórico, compara as modificações propostas, calcula o impacto estrutural e atualiza o `implementation_plan.md`. Este fluxo permanece ativo até que o usuário aprove o plano.
* **Aba Visual de Aprovação Centralizada (`📋 Aprovar Plano`)**: Em vez de exigir que o usuário digite comandos textuais de aprovação no chat, o painel central avisa que o plano foi salvo em `implementation_plan.md`, oferece campo para ajustes adicionais e botões de ação ("Aprovar e Codificar" ou "Ajustar Plano") para uma experiência interativa fluida.
* **Inicialização Automática de Workspaces**: Se uma pasta de workspace existente for selecionada no explorador, o backend FastAPI valida a existência do arquivo de rastreamento de estado (`state.json`). Caso esteja ausente, o backend cria e inicializa automaticamente o estado com valores padrão, garantindo que o explorador de arquivos e o chat funcionem instantaneamente sem retornar erros de 404. O workspace inicia sem `README.md`; documentação do projeto deve ser criada pelo Developer Agent quando fizer parte do plano aprovado.
* **Persistência de Métricas, Runtime Visual e Hardware Snapshots**: As métricas de inferência do Ollama (tempo total, contagem de tokens e Tokens por Segundo - TPS), o timer por fase, o status visual do agente em execução, snapshots de hardware e evidências silenciosas de qualidade são persistidos no `state.json`. Ao recarregar a interface, trocar de workspace ou clicar em arquivos durante uma execução, o frontend consegue reconstruir logs, timer, arquivos criados e preview do agente a partir desse estado.


### **4.2. Execução Segura e Escrita de Código**

Uma vez autorizado o plano, o workflow executa a seguinte cadeia de automação:

1. **Configuração do Git Local:** Cria-se o repositório Git local dentro do workspace. O sistema realiza commits silenciosos nos marcos relevantes do workflow, como plano gerado e arquivos concluídos pelo Developer.  
2. **Escrita de Código:** O Developer Agent escreve os artefatos físicos de forma concisa e direta.  
3. **Commit de Entrega:** O sistema faz o commit final no Git local com os arquivos gerados e atualiza o estado para concluído no `state.json`.  
4. **Falha Controlada:** Se o Developer não retornar blocos de arquivo válidos ou violar o sandbox, o workflow encerra como falha e registra o erro no `state.json`.

### **4.3. Interação Conversacional e Roteamento de Intenção**

No estado atual, o campo de chat da GUI funciona como **entrada de trabalho de desenvolvimento**. Portanto, qualquer nova mensagem enviada pelo usuário inicia novamente o fluxo `Planner Agent -> Aprovação -> Developer Agent`, mesmo quando a intenção real é apenas conversar, tirar uma dúvida ou perguntar sobre a execução anterior.

Para uma interação mais natural sem sobrecarregar a máquina, a evolução recomendada é adicionar um **Intent Router** leve antes do Planner. Esse roteador deve classificar a mensagem como:

1. **Conversa/pergunta:** responde usando o contexto do workspace, sem criar `implementation_plan.md` e sem acionar o Developer.
2. **Ajuste do plano atual:** envia feedback ao Planner quando houver plano pendente.
3. **Nova tarefa de desenvolvimento:** inicia o workflow completo de planejamento e aprovação.

A solução mais conservadora para o hardware atual é começar com um controle explícito de modo na UI ("Conversar" / "Desenvolver") ou um classificador leve usando `llama3.2-3b-local`. Evitar um terceiro agente sempre ativo mantém a demonstração mais rápida e previsível.

## **5\. Estrutura de Workspace, Segurança e Portabilidade**

Como o agente manipula a máquina nativa, barreiras lógicas rígidas protegem o sistema de arquivos local do Linux Mint ou Windows.

### **Estrutura do Workspace Local**

/home/\[usuario\]/swe-local-agent/  (ou C:\\swe-local-agent\\ no Windows)  
├── app\_backend/                      \# Código da IDE / FastAPI Orquestrador  
├── app\_gui/                          \# Interface Streamlit  
└── workspaces/                       \# Diretório Seguro Isolado (Sandbox)  
    └── \[id\_do\_projeto\]/  
        ├── .git/                     \# Histórico local silencioso  
        ├── .swe_local_agent/         \# Logs estruturados dos agentes  
        ├── src/                      \# Código-fonte gerado pela IA  
        └── tests/                    \# Testes opcionais gerados quando solicitados

### **Segurança e Multiplataforma (Linux / Windows)**

* **Prevenção de Fuga de Diretório (Path Traversal):** Toda ferramenta de escrita/leitura usa a biblioteca pathlib do Python. O sistema resolve o caminho absoluto (Path.resolve()). Se o caminho gerado não contiver o prefixo da pasta do projeto atual (/workspaces/[id_do_projeto]/), a operação de disco é imediatamente abortada com erro de segurança.
* **Otimização de Carregamento da Árvore de Arquivos**: O leitor de diretórios recursivo do frontend Streamlit ignora automaticamente pastas de dependência e ambientes virtuais comuns (`venv`, `.venv`, `node_modules`, `.vscode`, `.idea`, `.git`). Isso garante que a renderização do explorador de arquivos permaneça extremamente rápida e fluida, mesmo se o workspace contiver ambientes de desenvolvimento inteiros.
* **Comandos Proibidos:** O interpretador de terminal do agente barra comandos como sudo, rm -rf /, mkfs, format, chown ou modificações no registro do Windows.
* **Scripts de Inicialização Portáteis:** O projeto será inicializado por wrappers nativos: run.sh para Linux Mint e run.bat para Windows, configurando variáveis de ambiente de forma isolada.

## **6\. Interface do Usuário (Layout IDE SWE Local Agent)**

O layout foi desenhado para simular o VS Code, adaptado para telas de notebook comuns (1366x768 pixels):

* **Barra de Status:** Telemetria de hardware local (uso de CPU, uso de RAM, temperatura, workspace ativo e estado do LLM em CPU/GPU/misto).  
* **Coluna Esquerda (Explorador de Arquivos):** Árvore de diretórios física e interativa atualizada pelas ações do fluxo e pelos recarregamentos naturais do Streamlit.  
* **Coluna Central (Visualizador de Código):** Renderizador de código com realce de sintaxe e painel de log de execução. O editor manual foi removido para simplificar a demonstração e evitar conflito com processos de agentes em andamento.  
* **Coluna Direita (Chat Integrado de IA):**  
  * Campo de entrada de texto.  
  * Mensagens do usuário com destaque visual e borda azul.
  * **Visualização do "Thinking / Reasoning":** Quando o modelo local emite tags \<think\>...\</think\>, o chat captura esse trecho em tempo real e renderiza em um painel expansível com visual diferenciado antes de mostrar a resposta final. O plano completo não é despejado no chat; ele fica salvo em `implementation_plan.md`.
  * **Progresso do Planner:** Enquanto o plano é gerado, o chat mostra status e contagem de caracteres recebidos, sem exibir o plano inteiro na conversa.
* **Painel de Logs de Execução:** Logs ao vivo das etapas do Planner e Developer, incluindo métricas de tempo, tokens e TPS. Evidências de qualidade detalhadas ficam no `state.json` para análise posterior, sem bloquear o fluxo principal.

## **7\. Diferenciais Técnicos Acadêmicos**

1. **Dashboard de Consumo de Hardware local:** O professor verá graficamente que o software mede CPU, RAM, temperatura, GPU integrada e memória compartilhada, provando a viabilidade de rodar múltiplos agentes sequenciais em hardware comum.  
2. **Histórico Local por Git:** Cada etapa relevante gera commits locais silenciosos no workspace, permitindo auditoria técnica da execução.  
3. **Fluxo Enxuto e Demonstrável:** A redução para 2 agentes diminui latência, consumo de contexto e custo de CPU, tornando a demonstração mais previsível em hardware local.
