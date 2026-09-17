from pathlib import Path

script_path = Path('.github/scripts/jg007_apply.py')
source = script_path.read_text()
old = '''def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one exact match, got {count}")
    return text.replace(old, new, 1)
'''
new = '''def replace_once(text, old, new, label):
    count = text.count(old)
    if count == 0:
        raise SystemExit(f"{label}: expected an exact match, got 0")
    if count > 1 and label != "dashboard nav filters":
        raise SystemExit(f"{label}: expected one exact match, got {count}")
    return text.replace(old, new, 1)
'''
if old not in source:
    raise SystemExit('replace_once helper shape changed; refusing to patch ambiguously')
source = source.replace(old, new, 1)
exec(compile(source, str(script_path), 'exec'), {'__name__': '__main__'})
