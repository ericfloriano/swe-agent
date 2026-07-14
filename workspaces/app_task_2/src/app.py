from src.models import Activity, User
from src.database import Database
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class App:
    def __init__(self):
        self.db = Database()

    def run(self):
        while True:
            print("1. Adicionar Atividade")
            print("2. Listar Atividades")
            print("3. Sair")
            choice = input("Escolha uma opção: ")

            if choice == '1':
                self.add_activity()
            elif choice == '2':
                self.list_activities()
            elif choice == '3':
                break
            else:
                logger.warning("Opção inválida")

    def add_activity(self):
        name = input("Nome da atividade: ")
        description = input("Descrição da atividade: ")
        activity = Activity(name, description)
        self.db.add_activity(activity)
        logger.info(f"Atividade '{name}' adicionada.")

    def list_activities(self):
        activities = self.db.get_all_activities()
        for activity in activities:
            print(f"ID: {activity.id}, Nome: {activity.name}, Descrição: {activity.description}")