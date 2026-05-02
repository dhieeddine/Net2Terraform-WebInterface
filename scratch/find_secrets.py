import json
import os

path = r'd:\Desktop\pfa2\webInterface\final-rag.ipynb'
with open(path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

for i, cell in enumerate(nb.get('cells', [])):
    source = "".join(cell.get('source', []))
    if 'AWS_ACCESS_KEY_ID' in source or 'AWS_SECRET_ACCESS_KEY' in source:
        print(f"Cell {i} source contains keys!")
        print(source)
    
    for output in cell.get('outputs', []):
        if 'text' in output:
            text = output['text']
            if 'AKIA' in text or 'AWS_ACCESS_KEY_ID' in text:
                print(f"Cell {i} output contains keys!")
                print(text)
        if 'data' in output:
            for mime, data in output['data'].items():
                if isinstance(data, str) and ('AKIA' in data or 'AWS_ACCESS_KEY_ID' in data):
                    print(f"Cell {i} output data contains keys!")
                    print(data)
