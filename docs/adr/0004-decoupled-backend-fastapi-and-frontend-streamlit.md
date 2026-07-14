# Desacoplamento de Frontend Streamlit e Backend FastAPI

Decidimos separar a arquitetura da aplicação em dois processos distintos: um frontend gráfico usando Streamlit (`app_gui`) e um backend orquestrador usando FastAPI (`app_backend`). O backend executa o runtime LangGraph dos agentes em tarefas assíncronas em segundo plano e mantém o estado persistido no workspace.

O frontend inicia fluxos por HTTP e acompanha tokens/status via Server-Sent Events (SSE). Essa escolha evita travar a interface enquanto o Ollama executa inferências longas em CPU e permite exibir raciocínio, resposta, logs e métricas conforme chegam.

Atualizacao de 2026-07-11: como o Streamlit pode recarregar ao clicar em arquivos ou mudar abas, o backend tambem persiste um `runtime` snapshot em `.swe_local_agent/state.json`. Esse snapshot guarda agente ativo, status, previews rolantes e arquivos criados, permitindo reconstruir a tela mesmo se o SSE oscilar ou o usuario interagir com o workspace durante uma execucao.
