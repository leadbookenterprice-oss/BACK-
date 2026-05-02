from decouple import config
import os
print(f"Current dir: {os.getcwd()}")
print(f"DATABASE_URL from decouple: {config('DATABASE_URL', default='NOT FOUND')}")
