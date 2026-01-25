# Guidelines & Bêtisier (Tips & Tricks)

Ce document regroupe les règles d'or, les erreurs récurrentes et les astuces pour le développement du Raytracer.

## 🚨 Règles Critiques (DO NOT IGNORE)

### 1. UI Refresh (Éditeur)
**Règle** : Si vous modifiez un état qui affecte l'affichage de l'interface (changement d'onglet, ouverture d'accordéon, visibilité d'un widget), vous **DEVEZ** lever le drapeau :
```python
state.needs_ui_rebuild = True
```
**Pourquoi ?** : L'éditeur utilise une liste de widgets mise en cache (`ui_list`). Si vous ne forcez pas le rebuild, vos changements de logique ne se refléteront pas à l'écran (ex: clic qui ne fait rien, bouton qui reste visible).

### 2. State "Dirty" (Rendu)
**Règle** : Si vous modifiez la scène (position objet, lumière, caméra), vous **DEVEZ** lever le drapeau :
```python
state.dirty = True
```
**Pourquoi ?** : Cela signale au moteur de *reset* l'accumulation du Path Tracing. Sans ça, vous verrez des "fantômes" de l'ancienne image superposés à la nouvelle.

### 3. Namimg & IDs
**Règle** : Le `registry` dans `state.builder.registry` est la seule source de vérité pour le lien ID C++ <-> Données Python.
**Piège** : Ne jamais supposer qu'un ID est contigu ou séquentiel. Toujours vérifier `if id in registry`.

## Développement C++ / Nanobind

- **Recompilation** :
  - Toute modification dans `src/` nécessite une recompilation.
  - **Commande** : `uv run setup_project.py` (Gère CMake + Copie du .pyd).
  - Si vous changez une signature de fonction exposée à Python, n'oubliez pas de mettre à jour le binding Nanobind correspondant.
- **Gestion Mémoire** :
  - Attention à l'ownership des objets passés entre Python et C++.
  - `del engine` dans `main.py` est explicite pour forcer le nettoyage Nanobind avant la fermeture de Python.

## Problèmes Courants (Bêtisier)

### "L'interface ne réagit pas aux clics"
- **Cause** : Vous avez ajouté un bouton mais oublié de l'ajouter à `ui_list`, ou alors `state.needs_ui_rebuild` n'a pas été appelé après l'événement qui devait l'afficher.

### "L'image clignote ou ne converge pas"
- **Cause** : `state.dirty` est mis à `True` à chaque frame (dans la boucle principale) au lieu de seulement sur événement. Cela empêche l'accumulation temporelle (SPP qui reste à 1).

### "Crash à la duplication d'objet"
- **Cause** : Tentative de copier un objet sans faire de `copy.deepcopy()`. Python passe par référence par défaut, donc modifier la copie modifie l'original dans le registre, corrompant l'état.

### "L'éditeur plante au démarrage (fenêtre noire)"
- **Cause** : Souvent lié à une ressource (texture/envmap) non trouvée. Le moteur C++ peut `exit()` brutalement si une assertion échoue. Vérifiez les chemins relatifs (toujours par rapport à la racine du projet).
