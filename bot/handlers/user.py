from bot.handlers import user_actions


class UserHandler:
    def __init__(self, bot):
        self.bot = bot
        self.store = bot.store

    def handle_callback(self, callback_query):
        return user_actions.handle_callback(self, callback_query)

    def handle_command(self, message, command, parameter):
        return user_actions.handle_command(self, message, command, parameter)
