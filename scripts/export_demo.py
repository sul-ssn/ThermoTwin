import json
from app.kostanay import make_kostanay

n = make_kostanay()
with open("data/demo-network.json", "w") as f:
    json.dump(n.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
print(f"{len(n.nodes)} nodes, {len(n.pipes)} pipes, {len(n.consumers)} consumers")
