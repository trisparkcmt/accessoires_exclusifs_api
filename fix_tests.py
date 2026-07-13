import re

with open('catalogue/tests.py', 'r') as f:
    content = f.read()

# Pour les instances de Parfum.objects.create qui n'ont pas stock_quantite
# on va ajouter "stock_quantite=10, " juste avant "categorie=" ou "actif="
content = re.sub(r'(Parfum\.objects\.create\([^)]*?)(categorie=)', r'\1stock_quantite=10, \2', content, flags=re.DOTALL)

with open('catalogue/tests.py', 'w') as f:
    f.write(content)
