# Usar LangGraph para Orquestração de Agentes

Decidimos utilizar o framework LangGraph para orquestrar o fluxo dos agentes locais. O grafo ativo do MVP é sequencial e enxuto:

```text
planner -> developer -> END
```

Essa escolha mantém o estado compartilhado entre planejamento e desenvolvimento, facilita persistência em `.swe_local_agent/state.json` e deixa espaço para adicionar novos nós no futuro sem reescrever o backend. Loops automáticos de QA/autocorreção ficaram fora do fluxo padrão para reduzir latência e custo de inferência local.
