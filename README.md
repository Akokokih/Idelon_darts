# Idleon Darts Solver — Steam Windows

Fondations Python préparées avec GitHub Spec Kit. Le solveur ne joue pas encore :
la détection visuelle, les adaptateurs Windows et le modèle de tir restent à construire
et à calibrer sur des captures réelles.

## État actuel

- Constitution, spécification, plan et 28 tâches définis.
- Onze tâches terminées (T001–T011), dont lecture des sessions externes.
- Formats de données validés, chargement de profils et contrôleur indépendant du bureau.
- Interfaces pour capture produit, perception, prédiction, sessions, rejeu et entrées.
- Commandes `status` et `validate-session` disponibles ; observe/replay/run réservées.
- 47 tests passent sous Python 3.12.15 sur macOS, données synthétiques uniquement.

Aucun taux de réussite en jeu, délai d’arrêt Windows ni trophée n’est encore validé.
Aucun profil fictivement calibré n’est livré. Les dépendances natives seront ajoutées
et figées quand leurs adaptateurs seront implémentés et testés.

## Démarrage sous Windows

Python 3.12 64 bits requis. Depuis PowerShell dans ce dossier :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m idleon_darts status
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Le statut indique les fonctions réellement disponibles. Le paquet de base n’a pas
de dépendance native et n’accède pas au bureau. L’installation par pip peut télécharger
les outils de construction du paquet. Les essais Windows restent à effectuer.

## Valider les captures depuis leur dossier privé

Laisse les captures et leur ZIP à l’extérieur de ce projet. Après installation :

```powershell
.\.venv\Scripts\python.exe -m idleon_darts validate-session "D:\CapturesPrivees\session.zip"
```

Un dossier de session contenant session.json, frames.csv, events.jsonl et frames/
est également accepté. La commande vérifie chaque image, ses dimensions et son
contenu, les bornes temporelles, les compteurs et les chemins. Elle ne copie rien,
n’extrait pas le ZIP et n’exécute aucun fichier de la session.

Une session encore en cours est refusée. Pour diagnostiquer une session interrompue,
utilise explicitement `--allow-partial` : le bilan indique alors `complete=false`.
Les marqueurs F6/F7 restent des annotations, pas des centres prouvés.

Le rejeu image par image est disponible par l’API `replay_frames`, avec les temps
réels et les segments. La commande `replay` complète reste indisponible tant que
la détection et le moteur de prédiction ne sont pas implémentés.

## Documents Spec Kit

- [Constitution](.specify/memory/constitution.md)
- [Spécification](specs/001-automatic-darts/spec.md)
- [Plan](specs/001-automatic-darts/plan.md)
- [Tâches et avancement](specs/001-automatic-darts/tasks.md)
- [Modèle de données](specs/001-automatic-darts/data-model.md)
- [Contrats](specs/001-automatic-darts/contracts/cli-and-recordings.md)
- [Validation](specs/001-automatic-darts/quickstart.md)

MVP suivant : US1, observer et analyser 20 tirs sans clic automatique. Les prochaines
tâches sont T012–T015 ; le réglage des repères et du vent dépend des captures privées.

## Séparation des données privées

Le collecteur temporaire et ses enregistrements restent dans un dossier extérieur
au projet. Ils ne sont ni une dépendance, ni des fichiers de test distribués, ni une
partie du livrable. Les interfaces `capture.py`/`session.py` du produit ne contiennent
pas le collecteur. Le lecteur lit les dossiers et ZIP externes sans copie ni extraction.

Les tests créent leurs données synthétiques dans des dossiers temporaires. `.gitignore`
exclut données et médias, et la construction refuse leur présence dans le projet.
Pour produire une archive source en dehors de ce dossier :

```powershell
.\.venv\Scripts\python.exe tools/build_release.py
```

L’archive contient uniquement les fichiers sources, tests synthétiques et documents
explicitement autorisés. Un dossier de sessions, média ou collecteur privé détecté
fait échouer la construction avant remplacement de l’archive précédente.

## Références

[GitHub Spec Kit](https://github.com/github/spec-kit),
[workflow officiel](https://github.github.com/spec-kit/quickstart.html).
La recherche et les sources techniques sont dans
[research.md](specs/001-automatic-darts/research.md).
