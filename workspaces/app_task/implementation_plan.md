# Plano de Implementação
## Arquitetura e Dependências

* Linguagem de Programação: Python 3.x
* Modulo principal: main.py
* Dependências:
	+ datetime (para manipulação de datas e horários)

## Lista de Arquivos com Caminhos Relativos

* `main.py`:
	+ Descrição: Aplicativo principal para controle de atividades diárias.
	+ Comportamento esperado: Exibir menu de opções, permitir usuário escolher atividade a realizar e exibir horário de conclusão da atividade.
* `pomodoro.py`:
	+ Descrição: Função para simular um pomodoro (25 minutos de trabalho + 5 minutos de descanso).
	+ Comportamento esperado: Simular o tempo de trabalho e descanso, exibindo a duração restante.

## Critérios de Aceite

* O aplicativo deve ser capaz de:
	1. Exibir menu de opções para escolher atividade.
	2. Permitir usuário escolher horário de conclusão da atividade.
	3. Simular um pomodoro com duração adequada.