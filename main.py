import redis

r = redis.Redis(
    host="82.156.154.96",
    port=6379,
    socket_connect_timeout=5
)

print(r.ping())