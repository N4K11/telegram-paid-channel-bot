from config import get_config, load_dotenv, validate_config
from store_py import create_store
from bot.app import SubscriptionBotApp


def main():
    load_dotenv()
    config = get_config()
    validate_config(config)

    store = create_store(config.data_file_path)
    app = SubscriptionBotApp(config, store)
    app.start()


if __name__ == "__main__":
    main()
