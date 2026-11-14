# Guide de validation prévu

## État actuel

L’application propose la calibration automatique, les séries de tirs automatiques
et l’export local pour analyse avec Codex. Voir les cinq étapes du README.
Le taux de 90 % reste à atteindre : dernier lot corrigé de 20 tirs, 16 rouges et zéro vie perdue.
Les commandes observe/replay/run
ci-dessous sont des critères d’acceptation pour la prochaine phase,
pas des commandes exécutables aujourd’hui. Utiliser `gui` ou `auto-run` pour les séries expérimentales.

## Vérifier les fondations aujourd’hui

Depuis la racine du projet sous Windows PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m idleon_darts status
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Le statut distingue les fonctions disponibles des commandes réservées. Deux tests
peuvent être ignorés car la création de liens symboliques n'est pas autorisée. L'environnement `.venv` propre au dépôt
contient DXcam 0.3.0, NumPy 2.5.4, comtypes 1.5.0 et MSS 10.1.0.
Les tests ne lisent aucune capture privée et n'envoient aucune entrée. Deux tests
natifs vérifient une fenêtre synthétique cachée et l'ouverture/fermeture de MSS,
sans lecture des pixels du bureau. Un essai réel distinct est consigné dans validation.md.

## Vérifier la capture Windows sans calibration

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[capture]"
Get-Process | Where-Object { $_.MainWindowTitle -match 'Idleon' } | Select-Object Id, MainWindowTitle, MainWindowHandle
.\.venv\Scripts\python.exe -m idleon_darts capture-check --window-id 123456 --frames 30 --delay 5
```

DXGI est sélectionné par défaut. Pour comparer le mode de compatibilité, ajouter
`--backend mss`. La commande affiche le backend et ne bascule pas automatiquement
en cas d'échec de DXGI. Le JSON contient aussi frames_over_16_67ms (budget 60 im/s).

Remplacer le HWND d'exemple par `MainWindowHandle`, puis mettre le jeu au premier
plan pendant les cinq secondes. Attendu : code 0, JSON avec 30 images, dimensions,
durées et `images_saved=false`, `inputs_sent=false`. Ces durées encadrent aussi les
gardes et la conversion BGR ; elles ne mesurent pas la latence de rendu du jeu.
Le diagnostic ne vérifie pas que les images contiennent le mini-jeu attendu.

La zone cliente doit rester entièrement sur l'écran principal. Une perte de focus,
fenêtre masquée/minimisée, géométrie/DPI modifiés ou erreur MSS entraîne le code 1.
Relancer le diagnostic après correction ; un profil de tir devra être recalibré si
sa géométrie change. Ctrl+C interrompt avec code 130. Aucun profil n'est requis.
Le garde ne garantit ni absence de recouvrement ni détection d'un changement de
focus qui revient entre deux lectures. L'essai optimisé à 3440 × 1392 donne environ
99 im/s avec DXGI, contre 19,6 avec MSS ; voir [validation.md](validation.md).
L'objectif moyen de 60 im/s est dépassé sur cet essai, sans garantie par image.
DXGI attend une nouvelle image ; une scène sans mise à jour pendant environ
100 ms entraîne un refus explicite plutôt que la réutilisation d'une image en cache.

## Calibration visuelle disponible

Installer `.[capture,vision]`, puis utiliser `calibrate-visual` et `check-calibration`
selon le [README](../../README.md). Le JSON des régions doit correspondre à la fenêtre
réelle ; la zone wind_none doit être annotée sur un texte None visible. Les sorties
de calibration, images et rapports restent hors dépôt, dans de nouveaux chemins.
Le profil produit n'autorise aucun tir automatique.

Résultats de cette passe : ajustement sur 360 images, contrôle sur 600 nouvelles
images, suivi du déplacement du personnage et un bullseye supervisé (+5).
Score final observé 13, deux vies. Les résultats ne valident pas un modèle de tir,
les vents non nuls ou les critères SC-001–005 ; voir [validation.md](validation.md).

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
