# Contrats prévus — commandes et enregistrements

## Commandes actuellement disponibles

- `idleon-darts status` : affiche un objet JSON, code 0, avec `stage=foundation`,
  `automatic_play_available=false`, `observation_available=false`,
  `replay_available=false` et `private_capture_included=false`.
- `idleon-darts validate-session <dossier-ou-zip-externe> [--allow-partial]` :
  valide les données en lecture seule, sans extraction de ZIP ni copie. Code 0 si
  la validation réussit, code 1 si la session est refusée ; erreurs d’arguments code 2.
  Un JSON indique validation=complete|partial, summary.complete, compteurs, nombre
  de séquences d’entrée, annotations humaines séparées et avertissements éventuels.
  Une session en cours est toujours refusée. Une session en erreur exige
  --allow-partial et ne devient pas une preuve de performance complète.
- `idleon-darts --version` : version du paquet.
- `idleon-darts calibrate-visual --window-id <HWND> --regions <JSON> --output <nouveau-dossier-prive> [--frames 240] [--delay 3]` :
  mesure un balayage sans entrée souris et écrit la calibration visuelle hors dépôt.
  Le JSON d'entrée contient scene, arm, board, anchor, wind_none, rectangles en
  pixels écran. wind_none est une annotation humaine du texte None réellement visible.
  30 à 1000 images ; balayage ≥25 degrés ; refus si moins de 90 % de lames détectées
  ou P95 de distance des droites au pivot >8 px. Ces seuils sont des choix de qualité,
  pas une validation de précision en jeu. Le profil créé n'arme aucun modèle de tir.
- `idleon-darts check-calibration --window-id <HWND> --calibration <dossier-prive> [--frames 240] [--delay 3] [--report <nouveau-JSON>] [--preview <nouveau-PNG>]` :
  contrôle fini sans entrée souris, 1 à 1000 images, avec compteurs de repères
  disponibles et motifs d'abstention. Le JSON privé optionnel conserve chaque
  observation ; l'aperçu optionnel montre les repères recalés. Une interruption de
  capture produit un bilan partiel avec complete=false et le code 1. Géométrie/DPI
  incompatibles refusés avant le premier grab. Les sorties restent hors dépôt.
  Ces commandes renvoient 0 si terminées, 1 si refus, 2 pour arguments invalides,
  130 sur Ctrl+C. Les diagnostics ne sont pas des sessions d'enregistrement v1.
- `idleon-darts capture-check --window-id <HWND> [--frames 10] [--delay 3] [--backend dxgi|mss]` :
  diagnostic Windows sans calibration, entrée synthétique ni sauvegarde. HWND
  positif décimal ou hexadécimal, 1 à 300 images, délai fini entre 0 et 30 secondes.
  La zone cliente physique doit être au premier plan et sur l'écran principal.
  Focus/visibilité/identité/rectangle/DPI sont contrôlés avant et après capture.
  Code 0 et JSON des dimensions/durées si terminé, incluant elapsed_seconds,
  effective_fps (débit mural), capture_ms_p95 (rang supérieur à 95 %) et
  frames_over_16_67ms (seuil 1000/60 ms), frames_over_100ms et backend ; 1 si capture refusée ; 2 pour
  arguments invalides ; 130 sur Ctrl+C. `status` annonce `screen_capture_implemented=true` ;
  cela ne signifie pas que l'observation avec détection est disponible.
  DXGI est le défaut, sans repli silencieux vers MSS. Il demande une nouvelle image
  à chaque acquisition et copie le tampon en BGR immuable ; aucune nouvelle image
  pendant environ 100 ms entraîne un refus. Aucun thread de capture ni cache vidéo.
  `status` expose capture_backends et default_capture_backend, sans import natif.
- Les commandes observe/replay/run ci-dessous sont reconnues mais réservées :
  elles renvoient le code 2 et un message d’indisponibilité, sans lecture de profil
  ni entrée bureau.

## Commandes du solveur (comportement cible restant à implémenter)

- `idleon-darts observe --profile <profil>` : sans entrée synthétique ; affiche état
  et confiance ; produit une session locale.
- `idleon-darts replay <session> --profile <profil>` : sans action sur le bureau ;
  produit les décisions et métriques comparées aux annotations.
- `idleon-darts run --profile <profil>` : démarre en pause ; activation explicite
  depuis le panneau/raccourci ; arrêt prioritaire ; pas d’achat ni de relance automatique.

Ces comportements décrivent le contrat futur, ils ne sont pas disponibles aujourd’hui.
Codes de sortie prévus : 0 terminé, 1 erreur de session, 2 configuration invalide.
Aucune commande ne téléverse de données.

## Import d’une session de calibration privée

Entrée attendue : `session.json`, `frames.csv`, `events.jsonl`, `frames/*.png`.
Le collecteur temporaire n’est pas une dépendance ni une partie distribuée du solveur.

- `session.json` : `schema_version=1`, `purpose`, `created_utc`, `region`, `target_fps`,
  `clock`, `timestamps`, `target_window`, versions, `status`, compteurs et erreur éventuelle.
- `frames.csv` : `frame_index,segment_index,capture_start_ns,capture_end_ns,file`.
  Une ligne par image écrite ; les indices peuvent avoir des trous. Les horaires
  sont des nanosecondes relatives à l’origine de session et ne sont pas déduits des FPS.
- `events.jsonl` : un objet par ligne ; `kind`, `t_ns`, et champs selon type.
  `mouse` : `action=down|up`, `x,y` relatifs à la zone, `segment`.
  `annotation` : `action=centre|autre`, `segment`, marqueur humain indicatif sans
  association automatique à un tir. `resume|pause` : bornes et motif.
  `dropped_frame` : index abandonné et raison.
- `status=in_progress|complete|error` : refuser automatiquement une session en cours ;
  une session partielle exige un signalement explicite et ne compte pas comme essai complet.

L’import valide dimensions, PNG décodables, chemins contenus dans la session,
chronologie, références et compteurs. Une archive importée doit être extraite avec
contrôle des chemins. Aucun fichier importé n’est exécuté. Un changement de focus
peut créer un segment incomplet ; ne pas apparier des clics à travers les pauses.
Les down/up hors zone ne sont pas collectés ; un clic orphelin reste inconnu.

## Lecteur implémenté (T010–T011)

API Python : `with open_session(path, allow_partial=False) as session`. La source
peut être un dossier ou un ZIP contenant une seule session, à la racine ou dans
un sous-dossier. Aucun membre n’est extrait ; `voir.html` et les fichiers de code
éventuels ne sont jamais exécutés. Les enregistrements situés dans une racine de
projet détectée sont refusés. Des racines supplémentaires peuvent être interdites.

- `session.summary` : résumé validé et indicateur complete ; `warnings` explicites.
- `session.frames` : index, segment, temps réels, chemin interne et empreinte SHA-256.
- `session.events` : événements triés par timestamp, ordre stable à égalité. Les
  bornes resume/pause sont contrôlées dans l’ordre du journal car elles sont émises
  synchroniquement. Des callbacks souris tardifs restent compatibles.
- `session.clicks` : paires down/up dans un même segment ; les orphelins ont une
  borne None. Tous ont result=unknown : des entrées ne prouvent pas un impact.
- `session.annotations` : marqueurs humains séparés, sans association automatique.
- `replay_frames(session)` : itérateur des frames décodées BGR avec segment et horaires.
  Le contenu de chaque image est revérifié contre l’empreinte de validation.

Le décodeur accepte le format RGB 8 bits non entrelacé du collecteur, filtres PNG
0 à 4. Il vérifie CRC, fin du flux zlib, tailles et dimensions. Palette, alpha,
transparence, entrelacement et animation sont explicitement refusés. Limites :
16 millions de pixels/image, PNG ≤64 Mio, index/événements ≤32 Mio chacun,
100 000 images, un million d’événements, 150 000 membres ZIP et 32 Gio déclarés
pour une archive. Ce n’est pas un lecteur universel de variantes PNG.

Les frames sont décodées une par une. Seuls index, événements et empreintes sont
conservés en mémoire, sans nouvelle cache d’images. Les liens symboliques, traversées,
chemins absolus Windows/Unix, noms ZIP ambigus, archives chiffrées, CRC invalides,
références et compteurs incohérents sont refusés. Les images non indexées sont
refusées dans une session complète ; une session partielle les ignore avec un
avertissement. Les données de test sont générées dans des répertoires temporaires
extérieurs au projet et ne constituent pas un jeu de captures livré.
