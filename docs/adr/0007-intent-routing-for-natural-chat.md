# Roteamento de Intenção para Chat Natural

Identificamos que o chat atual da GUI funciona como canal de trabalho de desenvolvimento. Depois que um workflow termina, qualquer nova mensagem enviada pelo usuário inicia novamente `Planner Agent -> aprovação -> Developer Agent`, mesmo quando a intenção é apenas conversar, tirar dúvida ou perguntar sobre a execução anterior.

Decidimos registrar como próxima evolução um roteador de intenção antes do Planner. Esse roteador deve classificar mensagens em três grupos: conversa/pergunta, ajuste de plano pendente ou nova tarefa de desenvolvimento. Mensagens conversacionais devem responder sem criar `implementation_plan.md` e sem acionar o Developer.

Para preservar desempenho no hardware local, a implementação recomendada é começar com um modo explícito na UI ("Conversar" / "Desenvolver") ou um classificador leve usando `llama3.2-3b-local`. Evitar um terceiro agente sempre ativo mantém a demonstração mais previsível.

Nota de 2026-07-11: o experimento de perfil rápido direto foi removido do fluxo ativo. A decisão atual é manter toda tarefa de desenvolvimento passando por Planner, revisão humana e Developer, para melhorar rastreabilidade, facilitar demonstração acadêmica e evitar confusão na interface. O roteamento conversacional continua como evolução futura.
