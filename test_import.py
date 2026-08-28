import sys
sys.path.insert(0, "D:/tgbot")
from src.presentation.bot import create_dispatcher, create_bot
print("Bot import OK")
dp = create_dispatcher()
print("Dispatcher created OK")
bot = create_bot()
print("Bot created OK")
print("All imports successful")