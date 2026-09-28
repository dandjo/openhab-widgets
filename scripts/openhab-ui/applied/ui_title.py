import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m"); exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
path = m.DB + "uicomponents_ui_page.json"
data, enc = m.detect(path)
hits = []
def walk(node):
    if isinstance(node, dict):
        cfg = node.get("config", {})
        if node.get("component") == "oh-label-item" and cfg.get("item") == "epex_spot_awattar_market_gross":
            assert cfg["title"] == "aWATTar Market Gross", cfg
            cfg["title"] = "aWATTar Gross"; hits.append(cfg)
        for v in node.values(): walk(v)
    elif isinstance(node, list):
        for v in node: walk(v)
walk(data["overview"])
assert len(hits) == 1, hits
print(hits)
if sys.argv[1] == "apply":
    open(path, "w", encoding="utf-8").write(m.encode(data, *enc)); print("written")
