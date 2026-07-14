import unittest
from src.app import App
from src.database import Database

class TestApp(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.app = App()

    def test_add_activity(self):
        activity_name = "Test Activity"
        activity_description = "This is a test activity."
        self.app.add_activity(activity_name, activity_description)
        activities = self.db.get_all_activities()
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].name, activity_name)
        self.assertEqual(activities[0].description, activity_description)

    def test_list_activities(self):
        activity_name = "Test Activity"
        activity_description = "This is a test activity."
        self.app.add_activity(activity_name, activity_description)
        activities = self.db.get_all_activities()
        output = []
        for activity in activities:
            output.append(f"ID: {activity.id}, Nome: {activity.name}, Descrição: {activity.description}")
        expected_output = [f"ID: 1, Nome: {activity_name}, Descrição: {activity_description}"]
        self.assertEqual(output, expected_output)

if __name__ == "__main__":
    unittest.main()