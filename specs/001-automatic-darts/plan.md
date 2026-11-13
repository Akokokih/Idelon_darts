# Implementation Plan: Solveur automatique de Throwy Darts

**Branch**: aucune branche Git créée ; identifiant de fonctionnalité `001-automatic-darts`.
**Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: spécification de `specs/001-automatic-darts/spec.md`.

## Summary

Construire un assistant local Windows pour observer puis jouer au mini-jeu Steam.
La chaîne prévue est capture → détection → estimation d’impact → décision temporelle
→ entrée souris → confirmation du résultat. La physique sera identifiée à partir
des observations ; aucune constante du jeu n’est supposée connue.

Le plan et la conception sont terminés. Les fondations et la lecture externe T001–T011 sont implémentées ;
les adaptateurs natifs, la détection et le modèle de tir restent à construire. Un outil de collecte ponctuel est préparé séparément pour les essais
privés : son code, ses enregistrements et son archive sont exclus du projet et du
rendu final. Le solveur final aura son propre mode observation, requis par FR-002.

## Technical Context

**Language/Version**: Python 3.12, 64 bits.
**Primary Dependencies**: MSS pour les pixels ; OpenCV et NumPy pour la vision et
l’estimation ; adaptateur Win32 par ctypes pour premier plan, DPI et entrées.
Les versions du solveur seront figées lors de l’implémentation après essai Windows.
Le collecteur temporaire utilise MSS 10.1.0 et pynput 1.8.1, séparément.
**Storage**: fichiers locaux versionnés par schéma ; profils JSON, images et index
CSV horodaté, événements JSONL. Aucun service distant.
**Testing**: unittest pour moteur et contrôles d’état ; rejeu de séquences annotées ;
tests d’intégration sur Windows et essais supervisés sur Idleon.
**Target Platform**: Windows 10/11, Steam, écran principal, fenêtre visible et stable.
**Project Type**: outil de bureau local avec commandes et panneau de contrôle minimal.
**Performance Goals**: viser 60 captures/s sans garantie ; utiliser les horaires réels.
Arrêt demandé ≤100 ms ; refuser des observations de plus de 100 ms.
**Constraints**: aucun clic sans activation explicite ; un seul tir en attente ;
suspension sur perte de premier plan, invalidation géométrique ou contexte inconnu.
**Scale/Scope**: un joueur, une fenêtre, un profil actif ; 20 tirs annotés pour
vérifier l’observation puis ensembles séparés pour entraînement et validation.

## Constitution Check

Avant recherche : cinq principes satisfaits par la conception, aucun écart demandé.
Après conception : mêmes conclusions, sous réserve des validations listées ci-dessous.

| Principe | Dispositif prévu | Preuve à obtenir |
|---|---|---|
| Pixels et mesures | adaptateurs écran/souris, données annotées | vidéo/images d’impacts réels |
| Calibration | profils de géométrie et contexte, mode sans clic | invalidation après déplacement |
| Contrôle | machine d’états, arrêt prioritaire, un tir en attente | tests de transition + Windows |
| Reproductibilité | chronologie monotone et rejeu déterministe | même décision sur même entrée |
| Réussite mesurée | jeux de données séparés, abstentions publiées | SC-001 à SC-005 dans Idleon |

La conformité de conception ne signifie pas que ces preuves ont déjà été obtenues.

## Project Structure

### Documentation (this feature)

```text
specs/001-automatic-darts/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
└── contracts/cli-and-recordings.md
```

`tasks.md` contient 28 tâches ; les onze premières sont terminées.

### Source Code (repository root)

Structure du paquet créée ; les interfaces précèdent les adaptateurs réels :

```text
src/idleon_darts/
├── models.py
├── cli.py
├── capture.py
├── perception.py
├── calibration.py
├── prediction.py
├── controller.py
├── windows_io.py
├── replay.py
└── session.py
tests/
├── unit/
├── replay/
└── windows/
```

**Structure Decision**: une application Python et un moteur indépendant des entrées
réelles ; les adaptateurs de capture et de contrôle sont remplaçables par le rejeu.
Les captures privées ne sont pas des fixtures distribuées avec le produit.

## Phase 0 — Research

Les choix techniques sont résolus dans [research.md](research.md). Le choix entre
modèle physique et modèle empirique est résolu comme une stratégie de comparaison,
sans attribuer de valeurs fictives au vent, à la gravité ou à la vitesse.
L’identification des paramètres est un travail expérimental, pas une ambiguïté
à résoudre en demandant une formule à l’utilisateur.

## Phase 1 — Design

1. Valider capture et horodatage, puis annoter centres, bras, vent et impacts.
2. Établir une détection fiable sur images de sessions distinctes ; conserver la
   confiance et la cause d’abstention au lieu de transformer l’inconnu en échec.
3. Comparer prédicteur empirique local et modèle balistique ajusté. Retenir le modèle
   validé avec la plus faible erreur d’impact ; refuser les contextes hors couverture.
4. Estimer la fenêtre de réussite et compenser le délai observé de l’adaptateur.
5. Exécuter la machine `PAUSED → OBSERVING → READY → SHOT_PENDING → OBSERVING`.
   Toute anomalie mène à `PAUSED` ; la fin de partie ne déclenche pas de navigation.
6. Évaluer sur rejeu puis sur 100 opportunités réelles supervisées avant usage autonome.

[Modèle de données](data-model.md), [contrats](contracts/cli-and-recordings.md),
[guide de validation](quickstart.md).

## Complexity Tracking

Aucune dérogation à la constitution. Aucun modèle d’apprentissage profond,
serveur ou lecture de mémoire n’est nécessaire au plan initial.
