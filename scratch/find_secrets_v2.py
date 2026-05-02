import json
import os

path = r'd:\Desktop\pfa2\webInterface\final-rag.ipynb'
with open(path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

for i, cell in enumerate(nb.get('cells', [])):
    source = "".join(cell.get('source', []))
    if 'AWS_ACCESS_KEY_ID' in source or 'AWS_SECRET_ACCESS_KEY' in source:
        print(f"Cell {i} SOURCE contains keys! (first 100 chars): {source[:100]}")
    
    for j, output in enumerate(cell.get('outputs', [])):
        found = False
        text = ""
        if 'text' in output:
            text = "".join(output['text'])
        elif 'data' in output and 'text/plain' in output['data']:
            text = "".join(output['data']['text/plain'])
        
        if 'AKIA' in text or 'AWS_ACCESS_KEY_ID' in text:
            print(f"Cell {i} OUTPUT {j} contains keys! (first 100 chars): {text[:100]}")
