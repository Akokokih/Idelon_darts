# Guide de validation prévu

## État actuel

Conception, fondations et lecteur externe terminés ; le solveur visuel et les tirs restent à implémenter. Les commandes observe/replay/run
ci-dessous sont des critères d’acceptation pour la prochaine phase,
pas des commandes exécutables aujourd’hui. Les tests Windows restent à réaliser.

## Vérifier les fondations aujourd’hui

Depuis la racine du projet sous Windows PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m idleon_darts status
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Attendu : statut `foundation`, jeu automatique indisponible et 47 tests réussis.
Les tests synthétiques ne lisent pas les captures et n’envoient aucune entrée.
Sur la machine de développement, ils ont été exécutés sur Python 3.12.15 avec
`PYTHONPATH=src`, sans installer de dépendance native. L’installation sous Windows
et les essais en jeu restent à réaliser.

## Valider un dossier ou ZIP externe aujourd’hui

Depuis le projet installé, sans déplacer les captures dans le projet :

```powershell
.\.venv\Scripts\python.exe -m idleon_darts validate-session "D:\CapturesPrivees\session.zip"
```

Attendu : JSON avec validation=complete et summary.complete=true. Le nombre
input_spans décrit des pressions/relâchements, pas un score ou des impacts confirmés.
Les annotations humaines sont séparées. Une erreur renvoie le code 1 et son motif.
Une session en cours est toujours refusée. Une session en erreur exige
`--allow-partial` ; le JSON indique alors partial et complete=false.

Lecture et rejeu d’images par l’API Python (sans entrée bureau) :

```python
from idleon_darts.session import open_session
from idleon_darts.replay import replay_frames

with open_session(r"D:\CapturesPrivees\session.zip") as session:
    for item in replay_frames(session):
        # item.frame.bgr : pixels ; start_ns/end_ns : temps réels
        # item.segment_index : segment séparé par les pauses
        print(item.frame_index, item.segment_index, item.frame.start_ns)
```

Les tests vérifient l’absence de nouvelles copies, y compris dans le cas ZIP.
Aucune donnée utilisateur n’est nécessaire pour exécuter les tests livrés.

## Collecte privée préalable

L’outil de collecte temporaire est remis séparément. Il ne doit être copié ni dans
le dépôt du solveur ni dans son archive finale. Fournir plusieurs courtes sessions,
avec différents emplacements et du vent nul puis non nul, sans changer de géométrie.
Vérifier une première séquence de 10 secondes pour éviter de collecter des images
noires ou la mauvaise zone. Vérifier le débit mesuré et les abandons.

## Validation après implémentation

Prérequis : Windows 10/11, Python 3.12 64 bits, Steam, mini-jeu visible au premier
plan sur l’écran principal, profil calibré, installation du solveur selon son futur README.

1. `python -m unittest discover -s tests` : vérifier arrêt, anti-doublon, âge des
   observations, résultats inconnus et invalidation de profil. Attendu : tous passent.
2. `idleon-darts replay <session> --profile <profil>` sur sessions annotées distinctes
   de l’apprentissage : mêmes décisions lors de deux rejouages ; aucune entrée bureau.
3. `idleon-darts observe --profile <profil>` : contrôler au moins 20 tirs manuels,
   repères et résultats ; aucune entrée synthétique. Masquer puis déplacer la fenêtre :
   état suspendu, profil invalidé selon le cas.
4. `idleon-darts run --profile <profil>` : démarrage en pause. Activer dans le jeu,
   superviser 100 opportunités et publier abstentions, tirs, centres et inconnus.
   Aucun double tir ; 80 tirs minimum et 90 % de centres parmi eux, objectifs SC-002/004.
5. Répéter 20 fois chaque cas arrêt, focus perdu et image périmée. Aucun tir après
   suspension ; délai d’arrêt demandé ≤100 ms à chaque essai. SC-003.
6. Vérifier SC-001 sur 100 tirs annotés, puis viser une série de neuf centres dont
   la séquence complète est conservée. SC-005 reste non validé sans cette preuve.

Les échecs et limites de couverture sont des résultats à publier, pas à exclure du bilan.
