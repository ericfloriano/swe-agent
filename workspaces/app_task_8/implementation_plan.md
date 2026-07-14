# Plano de Implementação

## Escopo entendido
O app será uma ferramenta simples para controle de atividades diárias em Python. Ele permitirá cadastrar, listar, concluir e remover atividades pelo terminal.

## Funcionalidades mínimas obrigatórias
1. **Cadastro de Atividade**: O usuário deve ser capaz de cadastrar uma nova atividade com um título e uma descrição opcional.
2. **Listagem de Atividades**: O usuário deve ser capaz de listar todas as atividades cadastradas.
3. **Conclusão de Atividade**: O usuário deve ser capaz de marcar uma atividade como concluída.
4. **Remoção de Atividade**: O usuário deve ser capaz de remover uma atividade.

## Fora de escopo
- Implementação de Pomodoro, cronômetro, timer ou agenda.
- Modularização excessiva, camadas, controllers, interfaces ou modelos separados para apps simples de terminal.
- Invenção aleatória, simulações, timers, Pomodoro ou abstrações que o usuário não pediu.

## Arquitetura e dependências
1. **Arquivos**: 
   - `main.py`: O arquivo principal onde o código principal do app será escrito.
   - `activity.py`: Um módulo para representar uma atividade com título, descrição e status (concluída ou não).
2. **Modulos**:
   - `utils.py`: Módulo para funções úteis como validação de entrada.

## Lista de arquivos com caminhos relativos
- `main.py`
- `activity.py`
- `utils.py`

## Critérios de aceite
1. O usuário consegue cadastrar, listar, concluir e remover atividades