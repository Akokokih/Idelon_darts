# Modèle de données

## Profile

`schema_version`, `profile_id`, `created_utc`, `window_rect`, `roi`, `dpi`,
`detector_version`, `model_version`, `calibration_coverage`.
ROI en pixels physiques, largeur et hauteur positives, contenue dans la fenêtre.
Toute géométrie/DPI différent invalide le profil. Ne pas réutiliser un profil
simplement parce que le nom de la fenêtre est identique.

## Observation

`observation_id`, `session_id`, `segment_index`, `capture_start_ns`, `capture_end_ns`,
`image_path`, `launcher_position`, `arm_angle`, `arm_direction`, `target_center`,
`target_radius`, `wind_features`, `confidence`, `invalid_reasons`.
Temps relatifs monotones ; fin ≥ début ; âge calculé depuis la fin de capture et
incertitude au moins égale à la durée du grab. Aucun champ visuel inconnu n’est
remplacé par zéro ; l’absence de vent doit être distincte d’un vent illisible.

## Shot

`shot_id`, `session_id`, `observation_ids`, `profile_id`, `predicted_impact`,
`impact_uncertainty`, `decision_ns`, `input_down_ns`, `input_up_ns`, `result_ns`,
`observed_impact`, `result`, `result_source`, `suspension_reason`.
Résultat parmi `centre`, `other`, `miss`, `unknown`. Seule une confirmation visuelle
ou annotation humaine compte dans une série confirmée ; pas d’interpolation d’un
résultat inconnu. Un tir ne peut être envoyé si un autre est encore en attente.

## Session

`schema_version`, `session_id`, `created_utc`, `profile_id`, `software_version`,
`segments`, `frames_written`, `dropped_frames`, `missed_schedule_slots`,
`unknown_results`, `attempted_opportunities`, `shots_sent`, `confirmed_centres`,
`best_confirmed_streak`, `status`, `errors`.
Distinguer opportunités, abstentions, tirs, annotations et résultats détectés.
Les fichiers privés importés portent une provenance et ne deviennent pas
implicitement des fixtures redistribuables.

## Transitions

- `PAUSED → OBSERVING` : activation explicite, fenêtre et profil compatibles.
- `OBSERVING → READY` : repères fiables et contexte couvert.
- `READY → SHOT_PENDING` : une entrée envoyée, horodatée ; réévaluer les préconditions.
- `SHOT_PENDING → OBSERVING` : résultat confirmé et nouvel état de jeu observé.
- Tout état → `PAUSED` : arrêt, perte de premier plan, erreur, délai dépassé,
  géométrie invalide ou images périmées.
- Tout état → `STOPPED` : fin de session, fermeture des ressources et bilan.

Un rejeu utilise les mêmes transitions avec un adaptateur sans entrées réelles.

## Fondations implémentées

Les dataclasses immuables Rect, Profile, WindowContext, Observation et Prediction
sont définies dans `src/idleon_darts/models.py`. Les temps sont fournis par l’appelant
sur une horloge monotone commune ; aucune lecture d’horloge dans le contrôleur.
`WindowContext` ajoute l’identité de la fenêtre au rectangle et au DPI.
`Prediction` lie observation, profil, version du modèle et contexte, et donne une
fenêtre temporelle valide ainsi qu’un disque d’incertitude d’impact.
Les coordonnées visuelles sont relatives à la ROI ; rectangle de fenêtre et ROI
sont en coordonnées écran physiques. L’angle est exprimé en radians.

Le contrôleur réserve une tentative juste avant le futur appel de l’adaptateur :
SHOT_PENDING inclut cette réservation afin d’empêcher un deuxième appel. Une
réservation n’est pas une preuve d’entrée envoyée ni de tir réussi ; la couche de
session devra enregistrer le reçu réel et traiter toute erreur comme résultat
inconnu. Une pause conserve le tir non résolu. Sa résolution explicite est requise
avant un nouvel armement ; un résultat inconnu ne reprend pas automatiquement.
Après confirmation, une image capturée avant la confirmation n’est pas réutilisée.

Les seuils de confiance doivent être fournis explicitement. Le délai de résultat
par défaut (3 s) est une configuration provisoire à mesurer, pas une constante du
jeu. L’existence de métadonnées de calibration ne prouve pas la validité du modèle.

## Sessions externes validées (T011)

`ValidatedSession` possède un résumé immuable, un index de `FrameRecord`, des
`RecordedEvent`, `ClickSpan` et annotations distinctes. Les pixels ne sont ni
copiés dans le projet ni conservés en cache ; les seules références restent externes.
`FrameRecord` conserve index, segment, début/fin réels, chemin interne et empreinte.
Le rejeu émet `RecordedFrame(frame_index, segment_index, frame)` dont `frame` est
le format BGR commun à la future capture produit.

Les abandons expliquent les trous d’indices ; cadence cible et cadence mesurée sont
séparées. Dans une session complète : tentatives = écrites + abandonnées ; nombre
et durée des segments, débit et références doivent être cohérents. Dans une session
interrompue explicitement acceptée : les tentatives perdues pendant l’erreur et le
segment final non fermé sont signalés. Aucun résultat d’impact n’est inventé.
