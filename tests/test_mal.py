import json
import requests

with open("token.json", "r") as f:
    tokens = json.load(f)

access_token = tokens["access_token"]

anime_id = 52991

response = requests.get(
    f"https://api.myanimelist.net/v2/anime/{anime_id}",
    headers={
        "Authorization": f"Bearer {access_token}"
    },
    params={
        "fields": "my_list_status"
    }
)

print("Status:", response.status_code)

if response.status_code == 200:
    anime = response.json()

    print("\nAnime:", anime["title"])

    list_status = anime.get("my_list_status")

    if list_status:
        print("\nYour MAL data:")
        print(json.dumps(list_status, indent=2))
    else:
        print("This anime is not in your MAL list.")
else:
    print("API request failed.")
    print(response.text)