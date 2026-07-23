import requests

data = requests.get(
    "http://82.156.154.96:8080/v1/objects?class=Dataset&limit=1&include=vector",
    headers={
        "Authorization":"Bearer yange74520"
    }
).json()


vector=data["objects"][0]["vector"]

print(len(vector))