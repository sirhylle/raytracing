# UI Design System & Charter

Ce document décrit le framework d'interface utilisateur (UI) utilisé dans l'Éditeur (`modes/editor`). 
L'UI est construite "sur mesure" par dessus PyGame (`modes/editor/ui_core.py`).

## 1. Philosophie : "Retained Logic, Immediate Build"

L'architecture UI est hybride :
*   **Retained** : Les widgets sont des objets persistants (`Button`, `Slider`) stockés dans une liste `ui_list`.
*   **Dynamic Rebuild** : Cette liste est **entièrement reconstruite** à chaque changement de contexte (changement d'onglet, ouverture de section).

**Le Cycle de Vie UI :**
1.  `state.needs_ui_rebuild = True` est déclenché.
2.  `main.py` appelle `rebuild_ui()`.
3.  `rebuild_ui()` vide `ui_list`.
4.  Les fonctions "Builder" (`layout_global.build_header`, `tab_scene.build`, etc.) instancient de nouveaux widgets et les ajoutent à `ui_list`.
5.  À chaque frame, `main.py` itère sur `ui_list` pour `draw()` et `handle_event()`.

## 2. Composants (Widgets)

Tous les widgets héritent de `UIElement` dans `ui_core.py`.

### `Button`
Bouton clickable simple ou toggle.
*   **Usage** : Actions (Save, Render) ou Choix de mode.
*   **Helper** : Utilisez `btn()` (méthode factory) pour créer et ajouter en une ligne.
*   **Props** :
    *   `toggle=True` : Le bouton reste enfoncé (état actif).
    *   `group=[...]` : Si fourni, agit comme un **Radio Button** (un seul actif dans le groupe).
    *   `corners={...}` : Dictionnaire pour arrondir des coins spécifiques (ex: `{'tl':4, 'bl':4}` pour le début d'une barre d'outils).

### `Label`
Texte statique ou dynamique.
*   **Usage** : Titres de section, infos valeurs.
*   **Props** :
    *   `text` : Peut être une `str` ou une `callable` (fonction qui retourne une str) pour du texte dynamique (ex: FPS).

### `Slider`
Barre de glissement horizontale.
*   **Usage** : Valeurs continues (Intensité, Roughness, Position).
*   **Props** :
    *   `power` : Facteur logarithmique.
        *   `1.0` : Linéaire.
        *   `>1.0` (ex: 2.0, 3.0) : Précision accrue dans les petites valeurs (bien pour l'intensité lumineuse).
    *   `get_cb` / `set_cb` : Getters/Setters pour lier la valeur directement au `state`.

### `NumberField`
Champ texte éditable (Float).
*   **Usage** : Entrée précise de valeurs.
*   **Comportement** : Clic pour éditer -> Passage en mode `typing_mode` (bloque les raccourcis ZQSD) -> Entrée pour valider.

### `Separator`
Ligne horizontale décorative.
*   **Usage** : Séparer visuellement des sections dans un panneau.

## 3. Charte Graphique (Theme)

Les couleurs sont définies dans `ui_core.py`. Ne pas utiliser de couleurs "en dur" (RGB), utiliser les constantes :

| Constante | Couleur (Aperçu) | Usage |
| :--- | :--- | :--- |
| `COL_PANEL` | Gris Foncé | Fond des panneaux latéraux. |
| `COL_BG`    | Gris Noir | Fond général. |
| `COL_ACCENT`| **Orange** | Éléments actifs, sliders, focus. |
| `COL_TEXT`  | Blanc Cassé | Texte principal. |
| `COL_BTN`   | Gris Moyen | Bouton au repos. |
| `COL_BTN_ACT`| Bleu/Gris | Bouton actif/cliqué. |

## 4. Structure des Panneaux

L'écran est divisé en deux zones :
1.  **Viewport (Gauche)** : Rendu 3D interactif.
2.  **Panel (Droite, largeur fixe `PANEL_W`)** : Interface de contrôle.

### Organisation Verticale (Standard)
Les builders doivent respecter ce flux vertical (coordonnée `y`) :
1.  `layout_global.build_header()` : Crée les contrôles fichiers et les onglets. Retourne le `y` disponible suivant.
2.  **Contenu de l'Onglet** :
    *   Accordéon ("Section A")
    *   Contrôles A...
    *   Séparateur
    *   Accordéon ("Section B")
    *   Contrôles B...
3.  `layout_global.draw_footer_status()` : Dessiné en dernier (bas du panneau).

### Pattern "Accordéon"
Pour ne pas surcharger l'UI, utilisez le pattern accordéon géré par `state.py` :
```python
# Dans un builder de tab (ex: tab_scene.py)
if btn(..., txt="> MA SECTION", callback=lambda: state.toggle_accordion("TAB_NAME", "SECTION_ID")):
    pass

if state.is_accordion_open("TAB_NAME", "SECTION_ID"):
    # ... Ajouter les widgets de la section ici ...
    y += hauteur_widgets
```

## 5. Comment ajouter un nouvel élément ?

1.  **Identifier l'onglet** : `tab_scene.py`, `tab_object.py`, etc.
2.  **Localiser la fonction `build()`** : C'est là que l'impératif se passe.
3.  **Ajouter le widget** : Utiliser `btn()`, `lbl()`, ou instancier `Slider()`.
4.  **Lier au State** : Assurez-vous que le callback modifie `state` et met `state.dirty = True` (pour le rendu) ou `state.needs_ui_rebuild = True` (si l'UI doit changer).

**Exemple rapide :**
```python
# Ajout d'un bouton "Reset Camera" dans tab_scene.py
btn(ui_list, 10, y, 140, 24, "Reset Cam", lambda: reset_cam(state))
y += 30
```
