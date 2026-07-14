# Plano Obrigatorio e GUI Simplificada

Data: 2026-07-11

## Contexto

Durante os testes com tarefas simples em Python puro, o perfil rapido direto reduziu uma chamada LLM, mas tambem gerou ambiguidades na experiencia: nem sempre ficava claro quando havia plano, quando o Developer deveria iniciar, como explicar o tempo total e por que determinados arquivos apareciam so no fim do ciclo.

O editor manual tambem competia com o fluxo agêntico. Ele ficava preso no arquivo aberto, nao oferecia uma experiencia de edicao robusta o suficiente para demo e podia confundir a interacao com agentes em execucao.

## Decisao

Toda solicitacao de desenvolvimento na GUI deve passar por:

1. Planner Agent gerando ou ajustando `implementation_plan.md`;
2. aprovacao humana explicita;
3. Developer Agent escrevendo arquivos de forma direta e concisa;
4. estado final `completed` ou `failed`.

O perfil rapido direto e o editor manual ficam removidos do fluxo ativo. A coluna central deve se concentrar em `Visualizador` e `Logs de Execucao`.

## Consequencias

* A demonstracao fica mais previsivel e mais facil de explicar.
* O tempo total do workflow passa a ser a soma do tempo ativo do Planner e do Developer.
* O frontend fica menos sujeito a conflito entre edicao manual e escrita automatica por agentes.
* A performance bruta pode ser menor do que no experimento rapido, mas o ganho de rastreabilidade compensa para o MVP academico.
* Melhorias futuras de velocidade devem focar em percepcao de progresso, Fast Start leve, prompts menores, modelos menores e streaming confiavel, nao em pular o plano.
