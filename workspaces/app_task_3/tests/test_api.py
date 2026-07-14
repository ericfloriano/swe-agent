import unittest
from src.routes.api import api

class TestAPI(unittest.TestCase):
    def test_create_activity(self):
        with app.test_client() as client:
            response = client.post('/api/activities', json={'description': 'Test Activity'})
            self.assertEqual(response.status_code, 201)
            self.assertIn('Activity created successfully', response.get_data(as_text=True))

    def test_list_activities(self):
        with app.test_client() as client:
            response = client.get('/api/activities')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Test Activity', response.get_data(as_text=True))

    def test_update_activity(self):
        with app.test_client() as client:
            response = client.put('/api/activities/1', json={'description': 'Updated Test Activity'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Activity updated successfully', response.get_data(as_text=True))

    def test_delete_activity(self):
        with app.test_client() as client:
            response = client.delete('/api/activities/1')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Activity deleted successfully', response.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()