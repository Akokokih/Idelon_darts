# Tasks: Solveur automatique de Throwy Darts

**Input**: [plan.md](plan.md), [spec.md](spec.md), recherche, modèle de données et contrats.
**Date**: 2026-11-13. **Périmètre terminé** : tâches T001–T012, fondations, validation des sessions
externes, rejeu et adaptateur de capture Windows. Les tâches T013–T028 restent ouvertes.

Les tests sont demandés par la constitution et le guide de validation. Ils sont
écrits avant les composants correspondants. Les marqueurs [P] identifient des
fichiers indépendants, pas une obligation de déléguer.

## Phase 1: Setup

- [x] T001 Créer le paquet Python 3.12 et les points d’entrée dans pyproject.toml, src/idleon_darts/__init__.py et src/idleon_darts/__main__.py ; sans dépendance native au stade des fondations.
- [x] T002 [P] Exclure les données privées et fichiers générés dans .gitignore ; créer tools/build_release.py avec une liste explicite des répertoires distribuables, refuser liens symboliques, médias, sessions et outils de collecte dans le projet ; tester l’exclusion dans tests/unit/test_release.py.
- [x] T003 [P] Définir les interfaces remplaçables capture, perception, prédiction, sessions, rejeu et entrées dans src/idleon_darts/capture.py, perception.py, prediction.py, session.py, replay.py et windows_io.py ; aucun adaptateur natif ni entrée synthétique à ce stade.

## Phase 2: Foundational

- [x] T004 Écrire tests/unit/test_models.py pour les contraintes « largeur et hauteur positives », « contenue dans la fenêtre », « fin ≥ début », vent absent distinct de vent illisible ; tester les nombres non finis et booléens refusés comme entiers.
- [x] T005 Implémenter Rect, Profile, Observation, Prediction, WindowContext et les enums dans src/idleon_darts/models.py ; « Aucun champ visuel inconnu n’est remplacé par zéro » ; invalider le profil si rectangle ou DPI diffèrent.
- [x] T006 [P] Charger et valider les profils JSON version 1 dans src/idleon_darts/calibration.py ; refuser données supplémentaires, schéma incompatible et couverture vide lors de l’armement ; tests dans tests/unit/test_calibration.py.
- [x] T007 Écrire tests/unit/test_controller.py : démarrage en pause, activation explicite, observation périmée/future, contexte ou vent inconnu, focus/géométrie/DPI changé, délai de résultat dépassé, absence de doubles tirs, résultat inconnu et réarmement avec tir non résolu.
- [x] T008 Implémenter la machine d’états indépendante du bureau dans src/idleon_darts/controller.py ; « Un tir ne peut être envoyé si un autre est encore en attente » ; revérifier les préconditions lors de la réservation du tir, invalider les observations après résultat et conserver l’identifiant d’un tir non résolu à travers les pauses.
- [x] T009 Ajouter la commande status et l’aide dans src/idleon_darts/cli.py, documenter les fonctions réellement disponibles dans README.md ; observe, replay et run renvoient une indisponibilité explicite sans aucun accès au bureau ; tests dans tests/unit/test_cli.py.

**Checkpoint** : fondations testables sans Windows, données réelles ni clics ; aucune
user story complète n’est déclarée terminée par ces tâches.

## Phase 3: US1 — Observer et calibrer (P1, MVP)

**Goal** : observer et analyser les tirs sans clic automatique.
**Independent Test** : 20 tirs manuels annotés, géométrie changée et résultats inconnus.

- [x] T010 [US1] Tester l’import de sessions externes et le rejeu sans copie de données dans tests/replay/test_external_session.py ; chemins hors session, archives malformées, PNG illisibles, chronologie et compteurs incohérents doivent être rejetés.
- [x] T011 [US1] Implémenter lecture seule des sessions externes dans src/idleon_darts/session.py et leur décodage dans replay.py ; « Un clic orphelin reste inconnu » ; aucune copie dans le dépôt, aucune exécution de fichiers importés.
- [x] T012 [P] [US1] Implémenter capture DXGI et MSS avec garde Windows dans src/idleon_darts/capture.py et windows_io.py ; DPI physique, premier plan et rectangle validés avant/après capture ; tests spécifiques dans tests/windows/test_capture.py. Débit réel optimisé environ 99 im/s à 3440 × 1392 dans Idleon (validation.md).
- [ ] T013 [US1] Annoter et évaluer centre, lanceur, angle/direction du bras, vent et résultats dans src/idleon_darts/perception.py à partir des captures externes ; conserver confiance et motifs d’abstention ; ne pas distribuer les captures annotées. Partiel : calibration colour-pca-v1 et contrôle sur nouvelles images implémentés, déplacement du lanceur suivi, vent None reconnu. Résultats, vents non nuls et évaluation annotée restent ouverts.
- [ ] T014 [US1] Relier observe au mode sans entrée avec affichage des repères et journaux externes dans src/idleon_darts/cli.py et session.py ; vérifier nouvelle calibration après déplacement/redimensionnement.
- [ ] T015 [US1] Évaluer 20 tirs puis SC-001 sur 100 tirs distincts, consigner mesures et limites dans specs/001-automatic-darts/validation.md ; aucun taux ne peut être déclaré sans données.

## Phase 4: US2 — Tirs automatiques (P2)

**Goal** : maximiser les centres en fonction du contexte, avec abstention explicite.
**Independent Test** : 100 opportunités supervisées, sans double lancer.

- [ ] T016 [US2] Préparer les tests de prédiction et latence sur séquences séparées dans tests/replay/test_prediction.py, avec vent nul/non nul, plusieurs positions, sens de balayage et images périmées.
- [ ] T017 [US2] Ajuster et comparer modèles empirique et balistique dans src/idleon_darts/calibration.py et prediction.py ; conserver version, incertitude et couverture ; mesurer pression/relâchement au lieu de le supposer.
- [ ] T018 [US2] Choisir la fenêtre de lâcher compensée du délai mesuré dans src/idleon_darts/prediction.py ; s’abstenir quand l’incertitude ne tient pas dans le centre ou le contexte n’est pas couvert.
- [ ] T019 [US2] Implémenter les entrées Win32 et l’arrêt prioritaire dans src/idleon_darts/windows_io.py ; relâcher tout bouton maintenu après suspension ; tests dans tests/windows/test_inputs.py.
- [ ] T020 [US2] Relier capture, perception, prédicteur, contrôleur et confirmation de résultat à run dans src/idleon_darts/cli.py ; aucune reprise automatique après suspension ni clic de navigation.
- [ ] T021 [US2] Mesurer SC-002/SC-004/FR-013 sur 100 opportunités et enregistrer les chiffres dans specs/001-automatic-darts/validation.md, incluant abstentions, inconnus et doubles tirs éventuels.

## Phase 5: US3 — Contrôle et bilan (P3)

**Goal** : contrôler la session et lire ses résultats confirmés.
**Independent Test** : sessions de test contenant pauses, erreurs et résultats inconnus.

- [ ] T022 [P] [US3] Tester compteurs, dénominateurs et séries dans tests/unit/test_statistics.py ; résultat parmi centre, other, miss, unknown ; un inconnu coupe une série confirmée.
- [ ] T023 [US3] Implémenter bilan local dans src/idleon_darts/session.py : opportunités, abstentions, tirs, centres, inconnus et meilleure série séparés.
- [ ] T024 [US3] Relier arrêt utilisateur, perte de focus et fin de partie au contrôle dans src/idleon_darts/cli.py et windows_io.py ; vérifier 20 fois chaque cas de SC-003 et consigner les délais dans specs/001-automatic-darts/validation.md.
- [ ] T025 [US3] Valider la série de neuf centres sur une séquence privée complète et documenter uniquement le résultat et le protocole dans specs/001-automatic-darts/validation.md.

## Phase 6: Polish et validation transversale

- [ ] T026 Figer les versions natives après essais Windows dans pyproject.toml et le fichier de verrouillage retenu ; n’ajouter aucune dépendance issue du collecteur temporaire sans besoin propre au solveur.
- [ ] T027 Mettre à jour README.md et specs/001-automatic-darts/quickstart.md avec les commandes réellement exécutables et les résultats mesurés.
- [ ] T028 Exécuter tous les scénarios de specs/001-automatic-darts/quickstart.md, analyser cohérence et constitution, puis produire l’archive avec tools/build_release.py ; vérifier zéro capture privée et zéro outil de collecte distribué.

## Dependencies & Execution Order

Setup → fondations → US1 → US2 → validation transversale.
US3 peut développer son bilan après les fondations sur résultats synthétiques ;
sa validation de contrôle dépend de l’intégration US2. T025 dépend des tirs réels.

- T004 précède T005 ; T007 précède T008 ; T006 et T008 utilisent T005.
- T009 utilise les interfaces ; la commande status ne dépend pas des adaptateurs.
- T010 précède T011 ; T012 peut être développé avec un écran synthétique en parallèle
  de T011. Les captures réelles sont nécessaires pour T013, T015, T017 et les validations.
- T016 → T017 → T018 → T020 ; T019 exige T008 et peut avancer après T017.
- T022 → T023 ; T024 et T025 nécessitent le chemin d’exécution réel T020.

## Parallel Examples

- US1 : T011 (session.py/replay.py) et T012 (capture.py/windows_io.py), après leurs prérequis.
- US2 : T018 (prediction.py) et T019 (windows_io.py), une fois modèle et contrat d’entrée fixés.
- US3 : T022/T023 (bilan) en parallèle de la préparation des essais T024, sans exécuter
  ces essais avant l’intégration réelle.

## Implementation Strategy

Les douze premières tâches sont terminées, sans modèle factice. L'accès au bureau
est limité au diagnostic explicite de capture sans entrée ni sauvegarde d'image.
Le premier incrément utilisateur complet reste US1 : observation, annotations et rejeu.
Passer ensuite aux tirs supervisés, puis aux statistiques et au trophée mesuré.
L’outil de collecte et les données privées restent dans un dossier extérieur au projet.
Les données utilisées dans les tests livrés sont entièrement synthétiques et temporaires.

## Dernière validation : timing et vent

Complément diagonal : reprise depuis zéro, vent bas-droite 3 mph calibré sur six
impacts exploitables (un autre impact masqué exclu). Le filtre des points proches
du lanceur sépare l'animation de la main du vol réel. Erreur maximale de validation
croisée 22,20 px ; marge 38,30 px, formule inchangée. Un tir automatique indépendant
a fait +5, score 55, deux vies. Le vent bas-droite 5 mph suivant a été refusé sans
entrée. Modèle actif privé : None, droite 6 mph, bas-droite 3 mph. Les autres
contextes et la validation statistique restent ouverts. 90 tests : 88 passent,
2 ignorés. Détails, coûts des deux sondes grises et limites dans validation.md.

90 tests : 88 réussis, 2 ignorés faute de droits de liens symboliques. Entrées natives
à clic unique, ajustement par points de vol et compensation de déclenchement
implémentés. Le prédicteur reconstruit sa vitesse après images répétées, sauts ou
changement de position/vent. La marge verticale et la projection de collision
ont leurs propres contrôles, distincts du mode radial historique.

Essais réels : un bullseye automatique à 4 mph ; après ajustement sur quatre
trajectoires à 6 mph, deux tirs automatiques ont fait +5 puis +3 depuis deux
positions. Score final 64, une vie. Changement de vitesse puis de direction :
arrêt sans clic vérifié. Seul le modèle actif à 6 mph possède les annotations de
trajectoire complètes ; les autres modèles privés sont des essais antérieurs.
Le mode continu, le classificateur automatique de résultat, les vents hors
couverture et les critères de réussite statistique restent ouverts.

## Historique des premières passes

T001–T012 terminées : 12/28. T013 partielle ; T014–T028 restent ouvertes. 75 tests exécutés sous
Windows : 73 passent et 2 sont ignorés faute de droits de création de liens symboliques.
Les quatorze tests de capture incluent garde simulée, pixels BGR, horodatage, invalidation
persistante et deux essais natifs : fenêtre synthétique cachée avec restauration DPI,
puis initialisation/fermeture MSS sans lecture du bureau. Un essai séparé a vérifié
la capture sur Idleon ; aucune détection visuelle ni aucun modèle ajusté ne sont
encore validés. Les tests T012
ont été exécutés en échec avant l'implémentation. T010 précédait aussi le lecteur T011.

La commande validate-session contrôle les dossiers et ZIP externes sans extraction,
sans copie ni écriture. Le rejeu fournit les pixels BGR, temps réels et segments ;
il ne fabrique ni observation détectée ni décision de tir. Chaque PNG indexé est
décodé pendant la validation, puis son empreinte est vérifiée avant rejeu.
Les marqueurs humains restent séparés des résultats et les clics incomplets ne sont
jamais appariés à travers les pauses. Les images et le collecteur restent hors projet.

Les commandes observe, replay et run restent réservées : le contrat de replay complet
nécessite encore perception et prédiction. Les prochaines tâches sont T013–T015 pour
achever le MVP US1. Aucun hook d’extension n’est configuré.

La commande capture-check teste la capture en mémoire sans profil, sans reconnaissance
et sans sauvegarde. MSS 10.1.0 est une dépendance optionnelle propre au produit.
Le verrouillage complet T026 reste ouvert pour les futurs composants. L'extra capture
est figé sur DXcam 0.3.0, NumPy 2.5.4, comtypes 1.5.0 et MSS 10.1.0.
La capture optimisée sur Throwy Darts donne environ 99 im/s à 3440 × 1392 avec DXGI
par défaut, contre 19,6 avec MSS. Neuf cents acquisitions DXGI mesurées, puis 300
par la commande publique ; image vérifiée, gardes conservés, aucune calibration.
L'objectif moyen de 60 im/s est dépassé sur cet essai ; limites dans validation.md.

Calibration visuelle réelle : 360 orientations ajustées, écart P95 des droites au
pivot 2,24 px. Contrôle indépendant sur 600 images : angle/cible/vent None disponibles
sur 600 ; direction estimée disponible sur 563 ; environ 70,3 im/s. Après déplacements
et bullseye : 120 images, 114 directions disponibles, environ 63,9 im/s.
Ces compteurs ne sont pas une mesure d'exactitude SC-001.

Six lancers enregistrés par un collecteur privé distinct, dont le tir de démarrage
et quatre tirs en partie : score final 13, deux vies, un bullseye confirmé par le
score +5. Deux clics préalables hors enregistrement restent séparés. Un retard
d'outil de 965 ms a causé un miss et une vie perdue. Tous les détails et limites
sont dans validation.md. Aucun modèle de tir n'est déclaré calibré ; FR-005, T015,
T017 et la validation de réussite restent ouverts. Le collecteur privé n'est pas livré.
