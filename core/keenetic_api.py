import requests
from configparser import ConfigParser

class KeeneticAPI:
    def __init__(self, config_file="kdw.cfg"):
        config = ConfigParser()
        config.read(config_file, encoding='utf-8')

        self.host = config.get('keenetic', 'host')
        self.port = config.getint('keenetic', 'port')
        self.user = config.get('keenetic', 'user')
        self.password = config.get('keenetic', 'password')
        self.base_url = f"http://{self.host}:{self.port}/api"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def login(self):
        # Keenetic uses a challenge-response mechanism for authentication.
        # This is a simplified example. We might need to adjust it based on the exact API version.
        try:
            # 1. Get challenge
            response = self.session.get(f"http://{self.host}:{self.port}/auth", timeout=5)
            response.raise_for_status()
            challenge = response.json().get('challenge')

            # 2. Create realm and hash
            # This part needs to be implemented according to Keenetic's documentation
            # For now, we'll assume a simpler login for demonstration
            
            # Placeholder for actual authentication logic
            # payload = {
            #     "login": self.user,
            #     "password": self.password # This will likely need to be a hash
            # }
            # response = self.session.post(f"{self.base_url}/login", json=payload, timeout=5)
            # response.raise_for_status()
            
            # For now, we will just print a message
            print("Authentication logic needs to be implemented.")
            return True

        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Keenetic router: {e}")
            return False

    def get_system_info(self):
        if not self.login():
            return {"error": "Authentication failed"}
            
        try:
            response = self.session.get(f"{self.base_url}/show/system", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

if __name__ == '__main__':
    keenetic = KeeneticAPI()
    info = keenetic.get_system_info()
    print(info)
