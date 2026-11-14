# Feature Specification: Solveur automatique de Throwy Darts

**Feature Branch**: aucune ; projet initialisé sans extension Git.

**Created**: 2026-11-13

**Status**: Spécification validée ; fondations, lecture externe et capture Windows T001–T012 implémentées ; US1–US3 ouvertes.

**Input**: « Explique-moi le jeu des fléchettes sur Idleon. En utilisant GitHub
Spec Kit, je voudrais faire un solveur automatique. Steam sur Windows : lecture
de l’écran et clics automatiques. »

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Observer et calibrer une partie (Priority: P1)

Le joueur choisit la fenêtre du jeu, enregistre ses tirs manuels et vérifie les
positions détectées avant d’autoriser le programme à agir.

**Why this priority**: les mouvements, le vent et les délais réels doivent être
observés pour calculer un tir fiable. Ce mode sert aussi seul à analyser ses tirs.

**Independent Test**: enregistrer puis relire 20 tirs manuels. Comparer les repères
affichés et les résultats reconnus avec une annotation humaine.

**Acceptance Scenarios**:

1. **Given** une fenêtre Steam visible, **When** le joueur lance l’observation,
   **Then** les repères du lanceur, du centre, du vent et du résultat sont affichés
   avec un niveau de confiance ; aucune entrée souris n’est envoyée.
2. **Given** un tir manuel enregistré, **When** le résultat est visible,
   **Then** le programme conserve les images horodatées, le contexte et le résultat
   ou signale explicitement que le résultat est inconnu.
3. **Given** une fenêtre déplacée ou redimensionnée, **When** le profil ne correspond
   plus, **Then** le programme demande une nouvelle calibration avant tout tir.

### User Story 2 - Déclencher automatiquement les tirs (Priority: P2)

Le joueur démarre manuellement une partie et active le solveur. Celui-ci recherche
le moment de lâcher qui maximise la probabilité de toucher le centre, en tenant
compte du mouvement observé, du vent, de la position du lanceur et du délai d’entrée.

**Why this priority**: c’est l’automatisation demandée, après validation de l’observation.

**Independent Test**: mener 100 tirs supervisés sur une configuration calibrée,
enregistrant chaque décision et chaque résultat pour contrôle humain.

**Acceptance Scenarios**:

1. **Given** un état reconnu et calibré, **When** une fenêtre de tir exploitable est
   détectée, **Then** un seul lancer est déclenché et le programme attend son résultat.
2. **Given** du vent ou une nouvelle position du lanceur, **When** le contexte change,
   **Then** la décision est recalculée ; un contexte hors calibration suspend le tir.
3. **Given** un clic dont le résultat n’est pas confirmé, **When** le délai d’attente
   expire, **Then** le programme se suspend sans renvoyer aveuglément un clic.

### User Story 3 - Contrôler et évaluer une session (Priority: P3)

Le joueur peut arrêter les tirs à tout moment et consulter le taux de centres,
la série maximale et les causes de suspension de sa session.

**Why this priority**: permet de vérifier la progression vers neuf centres consécutifs.

**Independent Test**: rejouer des sessions annotées contenant perte de premier plan,
fin de partie, arrêt demandé et images manquantes.

**Acceptance Scenarios**:

1. **Given** un mode automatique actif, **When** le joueur appuie sur la touche
   d’arrêt, **Then** aucune nouvelle entrée n’est envoyée après 100 ms et tout bouton
   maintenu est relâché. Un lancer déjà reçu par le jeu ne peut être annulé.
2. **Given** une session terminée, **When** le bilan est consulté, **Then** les tirs,
   résultats inconnus, centres confirmés et séries sont décomptés séparément.
3. **Given** la disparition du mini-jeu ou la perte de premier plan, **When** cet
   état est détecté, **Then** les tirs se suspendent et ne reprennent pas sans action
   explicite du joueur.

### Edge Cases

- Vent illisible ou contexte jamais vu : suspendre et proposer une capture.
- Fenêtre masquée, changée de taille ou déplacée sur un autre écran : invalider le profil.
- Centre occulté par les fléchettes précédentes : utiliser un repère stable validé
  ou suspendre ; ne pas déduire un centre depuis une détection incertaine.
- Lag ou captures de plus de 100 ms : suspendre les nouveaux tirs.
- Plateau stable mais personnage mobile : réestimer le contexte de chaque tir.
- Résultat inconnu : ne pas compter un centre ni une série confirmée traversant ce tir.
- Fin de partie, menu ou temps de recharge : attendre le joueur, sans achats ni clics de navigation.
- Arrêt pendant un maintien du bouton : relâcher le bouton et arrêter la session.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: fonctionner sur Idleon Steam Windows 10/11, fenêtre visible au premier plan,
  via lecture de l’écran et entrées souris ordinaires.
- **FR-002**: fournir un mode observation sans clic et un mode automatique explicitement activé.
- **FR-003**: enregistrer un profil lié à la géométrie de fenêtre et à l’échelle d’affichage.
- **FR-004**: détecter centre, lanceur, évolution du bras et indicateur de vent ;
  afficher la confiance et refuser une décision si un repère indispensable manque.
- **FR-005**: mesurer le déclenchement au clic ou au relâchement dans le jeu réel,
  ainsi que le délai observable entre décision et lancer.
- **FR-006**: sélectionner le moment du lancer à partir du contexte courant et
  d’une calibration applicable ; ne pas supposer un délai constant universel.
- **FR-007**: empêcher les doubles tirs jusqu’à confirmation du résultat ou suspension.
- **FR-008**: distinguer centre confirmé, autre impact, échec et résultat inconnu.
- **FR-009**: journaliser localement observations, décisions, impacts et paramètres
  nécessaires au rejeu. Ne capturer que la zone de jeu choisie.
- **FR-010**: permettre un rejeu hors jeu, sans entrée souris, avec comparaison aux annotations.
- **FR-011**: suspendre sur arrêt demandé, perte de premier plan, images périmées,
  changement de géométrie ou disparition du mini-jeu.
- **FR-012**: produire un bilan avec nombre de tirs, taux de centres confirmés,
  couverture des décisions, résultats inconnus et série maximale confirmée.
- **FR-013**: lors des rejouages et essais supervisés, mesurer et afficher le délai
  décision-entrée et signaler toute latence incompatible avec la fenêtre de réussite.

### Key Entities

- **Profil** : géométrie, échelle, repères et contexte de calibration.
- **Observation** : image datée, positions, mouvement, vent, confiance et âge de l’image.
- **Tir** : observations sources, décision, entrée envoyée, impact et résultat annoté.
- **Session** : version, profil, liste de tirs, statistiques et causes de suspension.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Ces critères sont des objectifs à vérifier, aucun résultat n’est encore acquis.

- **SC-001**: sur 100 tirs annotés et distincts des tirs de calibration, reconnaître
  correctement au moins 95 % des centres et des non-centres ; publier aussi les
  résultats inconnus et toutes les erreurs de classement.
- **SC-002**: sur 100 opportunités de tir supervisées dans les contextes calibrés,
  lancer au moins 80 fois et toucher le centre sur au moins 90 % des tirs envoyés.
  Publier tous les abstentions et échecs afin d’éviter une mesure sélective.
- **SC-003**: sur 20 essais de chacune des conditions arrêt, perte de premier plan
  et image périmée, n’envoyer aucun nouveau tir après suspension ; respecter les
  100 ms suivant l’arrêt demandé dans chacun des 20 essais correspondants.
- **SC-004**: sur 100 tirs supervisés, ne produire aucun double lancer.
- **SC-005**: viser une série de 9 centres consécutifs, confirmée par une séquence
  complète enregistrée dans le jeu ; ce résultat seul valide l’objectif trophée.

## Assumptions

- Le joueur ouvre le mini-jeu et relance les parties lui-même pour cette première version.
- Le centre rouge est la cible initiale ; le mode points pourra suivre.
- Windows 10/11 et écran principal à géométrie stable constituent la première cible.
  Les autres écrans et configurations exigent une calibration distincte.
- Le comportement au relâchement est rapporté par des joueurs ; il reste à confirmer.
- La loi physique, les seuils de confiance et l’effet exact du vent restent à mesurer
  avant l’implémentation du moteur de décision. Aucun modèle balistique n’est acquis.
- La spécification ne garantit ni un trophée ni un taux de réussite avant essais réels.
- Dépendance de validation : séquences réelles sur la configuration Windows du joueur,
  comprenant plusieurs positions et au moins du vent nul et du vent non nul.
- Hors périmètre initial : achats, navigation de compte, redémarrage automatique des
  parties, version mobile, entraînement à grande échelle et modification du jeu.
