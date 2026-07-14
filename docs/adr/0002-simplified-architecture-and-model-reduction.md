# Simplificação da Arquitetura e Redução de Modelos

Decidimos simplificar a arquitetura agêntica original devido às limitações de hardware local (CPU de 4 núcleos e necessidade de evitar swap em 20 GB de RAM). O fluxo padrão usa apenas dois agentes LLM locais:

1. `llama3.2-3b-local` ou equivalente leve para o **Planner Agent**.
2. `qwen2.5-coder-3b-local` ou equivalente para o **Developer Agent** no fluxo padrão.

`qwen2.5-coder-7b-local` fica disponível como alternativa de qualidade para tarefas maiores ou mais ambíguas, em que completude seja mais importante que latência. O QA Agent, inspeção DOM, Playwright, voz e imagem ficam fora do workflow padrão. O Developer Agent realiza a codificação direta dos arquivos previstos de forma concisa e com baixa temperatura para garantir determinismo. Essa decisão reduz chamadas LLM, melhora a previsibilidade da demonstração e diminui o consumo de contexto.
