import codecs
with open("datadump_utf8.json", "r", encoding="utf-8-sig") as f:
    content = f.read()
with open("datadump_final.json", "w", encoding="utf-8") as f:
    f.write(content)
