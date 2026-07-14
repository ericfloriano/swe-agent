import datetime

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