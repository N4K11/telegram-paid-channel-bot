class FSM:
    def __init__(self):
        self.states = {}  # user_id -> state
        self.data = {}    # user_id -> dict

    def set_state(self, user_id, state):
        self.states[user_id] = state
        if user_id not in self.data:
            self.data[user_id] = {}

    def get_state(self, user_id):
        return self.states.get(user_id)

    def set_data(self, user_id, key, value):
        if user_id not in self.data:
            self.data[user_id] = {}
        self.data[user_id][key] = value

    def get_data(self, user_id, key=None):
        user_data = self.data.get(user_id, {})
        if key:
            return user_data.get(key)
        return user_data

    def clear(self, user_id):
        self.states.pop(user_id, None)
        self.data.pop(user_id, None)
