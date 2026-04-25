import requests
import json

url = "https://whatsappgw.teluscrcmaroc.com/api/messages"

headers = {
    "Authorization": "Bearer 2babf38d4f632a7891d098db342252caf90e79f2e5b02b660f883805087ad8e2",
    "Content-Type": "application/json",
}

payload = {
    "messaging_product": "whatsapp",
    "to": "212643489808",
    "type": "template",
    "template": {
        "name": "tccs_leads_manager_demo",
        "language": {"code": "fr"},
        "components": [
            {
                "type": "header",
                "parameters": [
                    {
                        "type": "image",
                        "image": {
                            "link": "https://via.placeholder.com/600x400"
                        }
                    }
                ]
            },
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "parameter_name": "variable_1",
                        "text": "Zakariae"
                    },
                    {
                        "type": "text",
                        "parameter_name": "variable_2",
                        "text": "Merci pour votre confiance"
                    }
                ]
            }
        ]
    }
}

response = requests.post(url, headers=headers, json=payload, timeout=30)

print("STATUS CODE :", response.status_code)
print("HEADERS :")
print(dict(response.headers))
print("TEXT :")
print(response.text)

try:
    data = response.json()
    print("\nJSON FORMATTE :")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if "messages" in data and data["messages"]:
        print("\nMESSAGE ID :", data["messages"][0].get("id"))
except Exception as e:
    print("Erreur parsing JSON :", str(e))