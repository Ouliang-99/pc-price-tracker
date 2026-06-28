"""ดู field จริงของ marketplace dataset จาก run ล่าสุด."""
import json
from app.config import setup_logging, settings
from apify_client import ApifyClient

setup_logging()
client = ApifyClient(settings.apify_token)
last = client.actor(settings.actor_marketplace).last_run()
run = last.get()
print("status:", run.status, "| dataset:", run.default_dataset_id)

items = list(last.dataset().iterate_items())
print("items:", len(items))
if items:
    print("\n=== keys ===")
    print(list(items[0].keys()))
    print("\n=== item แรก (ตัด field ยาว) ===")
    sample = {k: (str(v)[:140] if v is not None else None) for k, v in items[0].items()}
    print(json.dumps(sample, ensure_ascii=False, indent=2))
