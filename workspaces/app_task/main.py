import datetime

def show_menu():
    print("Menu de Opções:")
    print("1. Realizar Atividade")
    print("2. Simular Pomodoro")
    print("3. Sair")

def get_activity_completion_time():
    while True:
        try:
            completion_time = input("Digite o horário de conclusão da atividade (formato HH:MM): ")
            return datetime.datetime.strptime(completion_time, "%H:%M")
        except ValueError:
            print("Formato inválido. Por favor, digite novamente.")

def main():
    while True:
        show_menu()
        choice = input("Escolha uma opção: ")

        if choice == '1':
            completion_time = get_activity_completion_time()
            print(f"Atividade marcada para {completion_time.strftime('%H:%M')}")
        elif choice == '2':
            pomodoro()
        elif choice == '3':
            print("Saindo do aplicativo.")
            break
        else:
            print("Opção inválida. Por favor, escolha novamente.")

def pomodoro():
    work_time = datetime.timedelta(minutes=25)
    rest_time = datetime.timedelta(minutes=5)

    for _ in range(4):  # 4 rounds of Pomodoro (80 minutes total)
        print("Tempo de Trabalho:")
        while datetime.datetime.now() < completion_time:
            pass
        print("Descanso:")
        while datetime.datetime.now() < completion_time + rest_time:
            pass

if __name__ == "__main__":
    main()