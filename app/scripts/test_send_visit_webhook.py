from __future__ import annotations

import json
import urllib.request


URL = "https://wafa-api.swiftnova.ma/api/webhooks/visits"


payload = {
    "correlationId": "TEST-CAMPAGNE-001",
    "externalClientId": "RC00000001",
    "blockId": "TEST-BLOCK-DA-001",
    "fullName": "Timothée Marie",
    "phone": "+212643489808",
    "email": "zakariaezitane@gmail.com",
    "region": "Drâa-Tafilalet",
    "agence": "Agence Centrale",
    "plannedDate": "",
    "visitMode": "A_DISTANCE",
    "visitPurpose": "COMMERCIAL",
    "objectifs": [
        {
            "description": "Test webhook depuis la plateforme marketing automation pour valider l'envoi d'une visite commerciale."
        }
    ],
}


def main() -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8", errors="ignore")
            print("STATUS CODE :", response.status)
            print("RESPONSE    :", body)

    except Exception as e:
        print("ERROR :", repr(e))


if __name__ == "__main__":
    main()