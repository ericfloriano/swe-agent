from flask import Blueprint, request, jsonify
from src.models.activity import Activity

api = Blueprint('api', __name__)

@api.route('/activities', methods=['POST'])
def create_activity():
    data = request.get_json()
    Activity.add(data['description'])
    return jsonify({'message': 'Activity created successfully'}), 201

@api.route('/activities', methods=['GET'])
def list_activities():
    activities = Activity.list()
    return jsonify([{'id': a.id, 'description': a.description, 'date': a.date} for a in activities])

@api.route('/activities/<int:id>', methods=['PUT'])
def update_activity(id):
    data = request.get_json()
    Activity.update(id, data['description'])
    return jsonify({'message': 'Activity updated successfully'})

@api.route('/activities/<int:id>', methods=['DELETE'])
def delete_activity(id):
    Activity.delete(id)
    return jsonify({'message': 'Activity deleted successfully'})