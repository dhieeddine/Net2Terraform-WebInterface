import json

path = r'd:\Desktop\pfa2\webInterface\final-rag.ipynb'
with open(path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Cell 62: Remove hardcoded keys in source
source_62 = nb['cells'][62]['source']
new_source_62 = []
for line in source_62:
    if 'os.environ["AWS_ACCESS_KEY_ID"] =' in line:
        new_source_62.append('os.environ["AWS_ACCESS_KEY_ID"] = "YOUR_ACCESS_KEY_HERE" # REMOVED FOR SECURITY\n')
    elif 'os.environ["AWS_SECRET_ACCESS_KEY"] =' in line:
        new_source_62.append('os.environ["AWS_SECRET_ACCESS_KEY"] = "YOUR_SECRET_KEY_HERE" # REMOVED FOR SECURITY\n')
    else:
        new_source_62.append(line)
nb['cells'][62]['source'] = new_source_62

# Clear ALL outputs to be safe and reduce file size
for cell in nb['cells']:
    cell['outputs'] = []
    if 'execution_count' in cell:
        cell['execution_count'] = None

with open(path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)

print("Cleaned final-rag.ipynb: Hardcoded keys removed from Cell 62 and all outputs cleared.")
