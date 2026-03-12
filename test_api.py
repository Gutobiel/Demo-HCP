import requests
import json
import time

session = requests.Session()
URL = "http://localhost:8000/api/chat/"

def send_message(msg):
    print(f"\nUser: {msg}")
    try:
        response = session.post(URL, json={"message": msg}, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
        print(f"Agent: {data.get('response')}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response:
            print(e.response.text)

if __name__ == "__main__":
    send_message("Oi, preciso de pneu")
    time.sleep(2)
    send_message("Corolla")
    time.sleep(2)
    send_message("Acho que 2018")
    time.sleep(2)
    send_message("aro 16")
    time.sleep(5) # wait longer for scraper + openai
    # The last response should give recommendations from the site.
