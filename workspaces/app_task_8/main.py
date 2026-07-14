from activity import Activity
import utils

def menu():
    print("1. Cadastrar Atividade")
    print("2. Listar Atividades")
    print("3. Concluir Atividade")
    print("4. Remover Atividade")
    print("5. Sair")

def main():
    activities = []
    while True:
        menu()
        choice = input("Escolha uma opção: ")
        if choice == '1':
            title = input("Título da atividade: ")
            description = input("Descrição (opcional): ")
            activity = Activity(title, description)
            activities.append(activity)
            print("Atividade cadastrada com sucesso!")
        elif choice == '2':
            utils.list_activities(activities)
        elif choice == '3':
            title = input("Título da atividade a concluir: ")
            for activity in activities:
                if activity.title == title:
                    activity.mark_as_completed()
                    print("Atividade concluída!")
                    break
            else:
                print("Atividade não encontrada.")
        elif choice == '4':
            title = input("Título da atividade a remover: ")
            for i, activity in enumerate(activities):
                if activity.title == title:
                    del activities[i]
                    print("Atividade removida!")
                    break
            else:
                print("Atividade não encontrada.")
        elif choice == '5':
            print("Saindo...")
            break
        else:
            print("Opção inválida. Tente novamente.")

if __name__ == "__main__":
    main()