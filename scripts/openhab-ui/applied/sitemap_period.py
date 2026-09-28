import importlib.util, sys
spec = importlib.util.spec_from_file_location("m", "/tmp/awattar_migrate.py")
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m"); exec(compile(src, "m", "exec"), m.__dict__)
path = m.DB + "uicomponents_system_sitemap.json"
data, enc = m.detect(path)
changed = []
def walk(node):
    if isinstance(node, dict):
        cfg = node.get("config", {})
        if node.get("component") == "Chart" and cfg.get("item") == "epex_spot_awattar" and cfg.get("period") == "D":
            cfg["period"] = "D-D"; changed.append(cfg)
        for v in node.values(): walk(v)
    elif isinstance(node, list):
        for v in node: walk(v)
walk(data)
assert len(changed) == 2, changed
print(changed)
if sys.argv[1] == "apply":
    open(path, "w", encoding="utf-8").write(m.encode(data, *enc))
    print("written")
