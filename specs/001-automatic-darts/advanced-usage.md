# Archive technique avant la version 0.6

Ces notes décrivent les versions antérieures. Pour utiliser la version actuelle, voir le README à la racine.

# Idleon Darts Solver — Steam Windows

Application Windows expérimentale : calibration visuelle, séries de tirs entièrement
automatiques et export des données pour analyser et corriger le modèle avec Codex.
La version 0.5 utilise l'algorithme à relâchement programmé. Son test de référence a donné **13 rouges sur 20 (65 %)**,
sept autres zones et aucune vie perdue, score 213 → 329. L'écart de relâchement
mesuré est de 0,84 ms en médiane et 1,23 ms au maximum ; cette précision Windows
ne suffit pas à rendre la visée fiable à 90 %. Cet algorithme est maintenant
chargé par défaut, avec calibration et modèle mémorisés entre les lancements.
Les parties et leur progression diffèrent entre ces lots, qui ne comparent
donc pas exactement la même difficulté.

Le modèle physique peut utiliser la politique `phase-clock-v2` : origine du projectile
ajustée sur les trajectoires, phase estimée sur plusieurs poses et attente de déclenchement
limitée à 45 ms. La recherche d’angle traite aussi les deux arcs des positions éloignées.
Les lectures de vent prennent en charge les chiffres cyan et violets, y compris à 12 mph.

Le modèle physique accepte aussi `input_overhead_ns` (0 par défaut, maximum 50 ms)
pour budgéter le temps de l'entrée native en plus du maintien demandé. Ce budget
avance l'appel Windows ; `trigger_delay_ns` reste le délai empirique après relâchement.
Les reçus gardent les horaires avant et après l'appel natif pour vérifier ce budget.

Avec `absolute_mouse_up: true`, le clic est préparé en avance (`press_lead_ms`,
30 ms par défaut) et le bouton est relâché à une échéance absolue. La durée
variable de l'appel d'appui n'allonge plus le maintien prévu. `planned_up_ns`
et `up_error_ns` dans l'export permettent de mesurer l'écart réel. Les profils
sans cette option gardent le comportement précédent.

**Toute la bande rouge compte comme une réussite.** Le centre est le point visé
pour garder une marge sur les bords. La calibration du délai peut utiliser les
plages de timing correspondant à la bande rouge utile, avec une marge près des
barres ; cela n'impose pas de toucher un pixel précis pour compter un rouge.

## Lancer et collecter une série

1. Afficher Throwy Darts dans Idleon, puis ouvrir `Start-Idleon-Darts.cmd` ou l'exécutable Windows 0.5.0.
2. Choisir le nombre de tirs : **20** par défaut ; **0** pour continuer jusqu'à l'arrêt.
3. Cliquer sur **Lancer la série**. Sans profil enregistré, **Préparer et lancer** crée les repères et le modèle automatiquement avant de tirer.
4. Garder **Enregistrer les trajectoires** coché pour conserver les vols destinés à l'analyse.
5. À la fin, cliquer sur **Exporter pour Codex**. F8 ou le bouton Arrêter interrompt la série.

L’application lance, relit le résultat et recalcule la visée après chaque changement
de position ou de vent. Elle attend le résultat du tir avant de lancer le suivant.
Une lecture ambiguë suspend la série. Aucun clic manuel de lancer n’est demandé.

Le démarrage ne demande plus de charger un modèle ou de cocher une autorisation
séparée. La capture et le détecteur sont réutilisés pendant toute la série.
Le résultat est confirmé sur deux lectures stables avant de poursuivre ; l'attente
fixe de 2,5 secondes est supprimée dès qu'un résultat fiable est disponible.
Le test fonctionnel final a donné 5 rouges sur 5, sans vie perdue, avec des intervalles
entre tirs de 3,7 à 11,6 s et une confirmation médiane à 1,15 s après le lancer.
Ce petit test de fonctionnement ne remplace pas la mesure de précision sur 20 tirs.

Chaque série reste dans `../local/idleon-darts-app/reports/`. Le ZIP exporté contient
`shots.csv`, les observations JSON, les reçus du clic, les paramètres du modèle,
les images avant/après et les images de vol horodatées disponibles. `ANALYSIS.md`
explique les coordonnées et les vérifications pour une analyse ultérieure avec Codex.
L’export crée un fichier local ; il ne téléverse rien. La collecte de vol est bornée
à 48 images réduites par tir, acquises après le déclenchement puis encodées.
Les anciennes séries n’ont pas forcément d’images de vol.

## État actuel

- Constitution, spécification, plan et 28 tâches définis.
- Douze tâches terminées (T001–T012), dont lecture des sessions et capture Windows.
- Formats de données validés, chargement de profils et contrôleur indépendant du bureau.
- Interfaces pour capture produit, perception, prédiction, sessions, rejeu et entrées.
- Commandes `gui`, `auto-run`, `export-series`, `status`, `validate-session`, `capture-check`, `calibrate-visual`, `check-calibration`, `fit-model`, `auto-test` et `confirm-shot` disponibles ; observe/replay/run réservées.
- Calibration du pivot, de la lame, du panneau rouge, du repère du personnage et de la référence de vent `None`.
- Les tests utilisent des données synthétiques ; les captures et modèles mesurés restent hors dépôt.

La capture DirectX atteint environ **99 images/s** dans Idleon à 3440 × 1392,
sur trois séries de 300 images, avec les gardes actifs. Le P95 est d'environ 10,5 ms.
L'objectif moyen de 60 images/s est dépassé ; quelques captures dépassent 16,7 ms.
MSS reste disponible en compatibilité, à environ 19,6 images/s sur cette machine.
Voir les [mesures et limites](validation.md).
Ces mesures de capture sont historiques : la cadence dépend de la session et de la taille du jeu.
La cadence de capture ne prouve pas la cadence de rendu du mini-jeu.
Le taux de 90 %, le délai d’arrêt et le trophée ne sont pas validés.
Aucun profil fictivement calibré n’est livré. Les dépendances natives seront ajoutées
et figées quand leurs adaptateurs seront implémentés et testés.

Passe précédente : score 64, une vie restante. Un tir automatique avec vent
à droite de 4 mph a fait +5. Après calibration par suivi de trajectoire à 6 mph,
deux essais automatiques indépendants de l'ajustement ont fait +5 puis +3, depuis
des positions différentes. L'erreur maximale de validation croisée du modèle à
6 mph est de 11,2 px ; ce petit échantillon ne prouve pas un taux de réussite.
Dernière reprise : calibration du vent **3 mph en diagonale bas-droite**, six
impacts exploitables depuis différentes positions ; erreur maximale en validation
croisée 22,2 px. Un nouveau tir automatique a fait **50 → 55 (+5)**. Deux vies
restantes. Le passage suivant à 5 mph dans la même direction a déclenché un arrêt
sans clic. Ce nouveau vent n'est pas couvert par la calibration à 3 mph.
Les profils et enregistrements réels restent hors dépôt ; [protocole et limites](validation.md).

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
les outils de construction du paquet. Calibration et tirs en jeu restent à valider.

## Diagnostic de capture Windows sans calibration

Installer les adaptateurs optionnels (DXcam 0.3.0, NumPy 2.5.4, comtypes 1.5.0,
MSS 10.1.0, versions mesurées sous Windows) :

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[capture]"
Get-Process | Where-Object { $_.MainWindowTitle -match 'Idleon' } | Select-Object Id, MainWindowTitle, MainWindowHandle
.\.venv\Scripts\python.exe -m idleon_darts capture-check --window-id 123456 --frames 30 --delay 5
```

Le backend par défaut est `dxgi`. Ajouter `--backend mss` pour le mode de compatibilité.
Il n'y a pas de bascule silencieuse vers MSS en cas d'erreur DirectX. Un environnement
`.venv` propre à ce dépôt est préparé sur la machine de développement.

Remplacer `123456` par le `MainWindowHandle` de la fenêtre Steam du jeu (pas son Id
de processus). Pendant le délai, mettre cette fenêtre au premier plan. Elle doit
être entièrement visible sur l'écran principal. La commande capture sa zone cliente
sans bordures, puis affiche les dimensions et durées de capture ; elle ne sauvegarde
aucune image et n'envoie aucune entrée. Le JSON indique aussi le débit mural,
le backend, le P95 des durées et le nombre de captures dépassant 16,7 ms et 100 ms.
Ctrl+C interrompt le diagnostic.

La capture vérifie focus, visibilité Windows/DWM, identité, rectangle et DPI avant
et après chaque acquisition. Un déplacement, redimensionnement ou changement de DPI
invalide la source, même si la fenêtre revient ensuite à son emplacement initial.
Le diagnostic s'arrête à la première erreur (code 1). Une interruption donne le code
130 ; des arguments invalides donnent le code 2. Le nombre d'images est limité à 300.

Limites : ces vérifications ne détectent pas un aller-retour de focus entre deux
lectures, ni tous les éléments qui recouvrent le jeu. Le DPI est celui rapporté par
Windows pour la fenêtre cible ; une application sans conscience DPI rapporte 96.
Les coordonnées de capture restent physiques grâce au contexte DPI par moniteur
du thread, restauré après usage. Les tests natifs utilisent une fenêtre synthétique
cachée et initialisent MSS sans capturer le bureau ; les pixels BGR et changements
pendant capture sont testés avec un adaptateur simulé. Un essai réel sur l'écran
d'attente de Throwy Darts a confirmé les images MSS/DXGI et les débits décrits ci-dessus.
La barre de titre du jeu peut faire partie de sa zone cliente. Si Windows annonce
une zone hors écran, ajuster la fenêtre avant le diagnostic ; le garde reste strict.

DXGI utilise une acquisition synchrone de nouvelles images, puis une seule copie
du tampon BGR vers des octets immuables. Aucune image en cache n'est recomptée : si
aucune nouvelle image n'arrive, la capture attend en revérifiant le contexte et
échoue après environ 100 ms. Sur une scène statique ou un écran qui se rafraîchit
lentement, le débit peut donc baisser ou le diagnostic s'arrêter. Le débit mesuré
concerne l'acquisition du bureau, sans détection ni modèle de tir, et ne prouve pas
que le moteur du jeu rend autant d'images distinctes.

## Calibration visuelle et vérification sans clic

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[capture,vision]"
.\.venv\Scripts\python.exe -m idleon_darts calibrate-visual --window-id 123456 --regions "D:\CalibrationPrivee\regions.json" --output "D:\CalibrationPrivee\profil-01" --frames 360 --delay 5
.\.venv\Scripts\python.exe -m idleon_darts check-calibration --window-id 123456 --calibration "D:\CalibrationPrivee\profil-01" --frames 600 --delay 5 --report "D:\CalibrationPrivee\controle-01.json" --preview "D:\CalibrationPrivee\controle-01.png"
```

Remplacer le HWND d'exemple par celui du jeu. `regions.json` décrit cinq rectangles
physiques en coordonnées écran (`left`, `top`, `width`, `height`) : `scene` contient
tous les autres ; `arm` isole la lame pendant son balayage ; `board` contient le
panneau et sa zone rouge ; `anchor` contient un repère stable du personnage (ici sa
plateforme) ; `wind_none` contient le texte **None** du vent, vérifié visuellement.
Ces zones doivent être choisies sur l'affichage réel, sans recopier des coordonnées
d'une autre machine. Le mouvement doit couvrir au moins 25 degrés et 30 orientations.

La commande crée un nouveau dossier privé avec `profile.json`, `visual.json`, la
référence et les deux modèles visuels. Elle refuse un dossier existant et toute
sortie dans le dépôt. Le profil conserve `model_version=null` et une couverture
de tir vide : calibration visuelle et calibration de trajectoire restent distinctes.
Les paramètres de segmentation sont actuellement adaptés à la lame claire observée
dans cet essai ; une autre apparence peut nécessiter un nouveau détecteur.

`check-calibration` vérifie la géométrie et le DPI, puis produit les positions et
angles observés, une estimation du sens de balayage et des motifs d'abstention.
Il suit le déplacement de la plateforme par recherche du modèle visuel ; une
correspondance ambiguë, une cible occultée ou un vent sans référence restent
inconnus. Une bibliothèque privée optionnelle `wind-library.json` reconnaît les
vitesses et directions annotées ; les correspondances multiples sont refusées.
Le score de qualité est heuristique, pas une probabilité de réussite.
Les nombres du bilan indiquent la disponibilité des repères, pas leur exactitude
mesurée sur des tirs annotés. Ces deux commandes n'envoient aucune entrée souris.
`observe` reste réservé au futur mode complet avec journaux de session et résultats.

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

- [Constitution](../../.specify/memory/constitution.md)
- [Spécification](spec.md)
- [Plan](plan.md)
- [Tâches et avancement](tasks.md)
- [Modèle de données](data-model.md)
- [Contrats](contracts/cli-and-recordings.md)
- [Validation](quickstart.md)

Un essai automatique expérimental à un seul tir est disponible ; `run` reste réservé.
La validation sur 20 tirs et la calibration fiable des vents restent à terminer.

## Modèle empirique et essai automatique

`fit-model --calibration DOSSIER --samples IMPACTS.json --output MODELE.json`
ajuste deux coefficients de trajectoire par contexte, avec au moins quatre impacts
mesurés distincts. Le JSON contient une liste `samples` : contexte, position du
lanceur (`launcher_x`, `launcher_y`), angle en radians (`release_angle`) et impact
(`impact_x`, `impact_y`). Les coordonnées sont relatives à la région capturée.
On peut fournir `flight_points`, une liste ordonnée de positions (x,y) du même
repère sur la fléchette en vol, à la place de l'angle. Il faut au moins huit points,
300 px de portée et un résidu P95 inférieur à 3 px. Les points situés dans les
200 premiers pixels horizontaux depuis le pivot sont exclus : ils peuvent encore
suivre la fléchette tenue pendant l'animation de la main, dans la zone du lanceur.
Il faut huit points et 300 px de portée après cette exclusion. Cet ajustement évite de
confondre l'animation du bras après le clic avec l'angle de lancement.
Le modèle est lié au profil. Sa marge heuristique utilise l'erreur maximale de
validation en laissant chaque impact de côté ; cela ne prouve pas une précision
sur des données indépendantes. Le domaine horizontal tolère une extension de 10 %.

```powershell
.\.venv\Scripts\python.exe -m idleon_darts auto-test --window-id 10489658 --calibration "D:\Prive\profil" --model "D:\Prive\modele.json" --output "D:\Prive\essai-001" --arm
```

Le HWND et le point de clic (`--click-x`, `--click-y`, défaut 2400,900) doivent
correspondre à la fenêtre et à la scène courantes. Sans `--arm`, aucune entrée.
L'essai utilise seulement le balayage descendant, maintient le clic 1 ms par défaut et
s'arrête après un lancer. F8 interrompt. Focus, identité, géométrie, DPI, fraîcheur,
vent et marge d'impact sont vérifiés. Le modèle historique utilise une marge
radiale ; le modèle `empirical-launch-v2` utilise l'intervalle vertical rouge mesuré
au plan d'impact. La projection doit rester alignée avec la cible et son intervalle
d'incertitude entièrement contenu dans sa hauteur. Ce n'est pas une marge radiale
agrandie. La prévision est reconstruite après changement de position, de vent,
blocage des poses ou saut d'angle. Une répétition brève ne remplace pas l'horodatage
de la dernière pose distincte.

Le modèle v2 conserve dix poses distinctes et peut utiliser
`theta(t) = theta_mesuree + omega*t + alpha*t*t/2` pour prévoir le passage à
l'angle de visée. L'accélération doit être supérieure au bruit estimé, respecter
les bornes de vitesse et expliquer deux poses retirées d'un ajustement séparé
mieux que la prévision linéaire. Sinon, une vitesse locale stable sur six poses
est utilisée, ou le tir est refusé. Le calcul rejette aussi les changements de
sens avant le clic, y compris après correction de phase. Les délais natifs,
la couverture du vent et les marges complètes restent contrôlés. Les rapports
`auto-test` indiquent la politique de prévision et, si un tir est envoyé, les
valeurs de vitesse, d'accélération et le choix effectivement utilisé.
Une correction de phase calibrée avec la prévision linéaire doit être réévaluée
avec cette nouvelle politique avant de revendiquer une précision en automatique.

`fit-model --trigger-delay-ms 20 --target-x-offset -31.5` a servi au dernier modèle
privé, avec les points de vol à 6 mph. Ces valeurs sont propres à cet essai : délai
empirique entre l'entrée planifiée et l'angle effectif, puis projection du centre
visuel sur la ligne de collision mesurée. La commande conserve ces valeurs dans
le modèle. Les temps avant et après chaque appel SendInput sont journalisés ;
ils bornent l'appel natif, sans garantir le temps de traitement dans le jeu.

L'angle historique `arm_angle` mesure l'axe blanc de la fléchette tenue en main.
Sa direction de déplacement initiale est estimée séparément sur les points de vol.
L'inversion de l'équation d'impact résout une équation du second degré en
`tan(angle)`, puis conserve une solution dans le domaine calibré (arc bas en priorité).
Une cible hors de portée ou hors de ce domaine reste refusée.

Chaque contexte du modèle v2 peut préciser ensemble `phase_correction_ns` et
`end_to_end_uncertainty_px`. Une correction positive retarde la commande, dans
la limite de ±100 ms ; elle décrit un déphasage empirique entre affichage, entrée
et vol, sans identifier une latence interne du jeu. La marge utilisée est le
maximum de la marge de trajectoire et de celle mesurée de bout en bout. Une
bonne courbe ajustée aux points de vol ne suffit donc plus à autoriser le tir
si le déclenchement reste trop variable. Ces champs doivent être calibrés pour
chaque vent couvert ; aucune vitesse voisine n'est substituée automatiquement.

Après observation du résultat, `confirm-shot --calibration DOSSIER --result
centre|other|miss|unknown --source "observation du score"` consigne l'annotation.
Une réservation privée interdit un second essai tant que ce résultat reste en attente.
`auto-test` reste limité à un essai avec confirmation ; `auto-run` enchaîne les tirs et lit les résultats.
Les sorties de modèle et d'essai doivent rester hors du dépôt.

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
[research.md](research.md).
