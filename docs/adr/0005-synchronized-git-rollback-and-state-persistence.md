# Sincronização de Rollback do Git com o State Memory Tracker

Decidimos salvar a estrutura de dados do `State Memory Tracker` diretamente no workspace em `.swe_local_agent/state.json` e incluí-la nos commits automáticos do repositório Git local. Toda vez que Planner ou Developer conclui uma etapa relevante, o backend grava o estado JSON e realiza commit incluindo estado e arquivos gerados.

O frontend atual não exibe mais a aba de rollback visual para manter a UI simples. O histórico Git continua existindo no workspace e pode ser auditado via terminal ou por futuras extensões da interface.
