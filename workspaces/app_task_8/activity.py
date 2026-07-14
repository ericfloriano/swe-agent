class Activity:
    def __init__(self, title, description=None):
        self.title = title
        self.description = description
        self.completed = False

    def mark_as_completed(self):
        self.completed = True

    def __str__(self):
        status = "Concluída" if self.completed else "Pendente"
        return f"{self.title} - {status}"