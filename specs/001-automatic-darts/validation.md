# Validation — 13 novembre 2026

## Reprise et calibration du vent diagonal

Au retour, le jeu était déjà à zéro avec vent None. Six sondes ont donné
0 → 5 → 10 → 13 → 18 → 23 → 33, sans perte de vie. Le dernier gain comprenait
un bonus affiché ; quatre vies étaient visibles. Le vent suivant était de 3 mph
en diagonale bas-droite, distinct du vent diagonal à 6 mph de la passe précédente.
Une nouvelle référence privée comprend vitesse et direction ; la vitesse n'est
jamais réutilisée seule comme identifiant de contexte.

Cinq sondes diagonales ont fait 33 → 36 → 39 → 42 → 47 → 50. L'impact de la
troisième est presque entièrement masqué par une ancienne fléchette : il est exclu
de l'ajustement. Les quatre autres trajectoires seules donnaient initialement une
erreur maximale de validation croisée de 52,33 px. Deux points supplémentaires,
haut et bas sur les zones grises, ont conservé le score 50 mais coûté deux vies.
Deux tentatives intermédiaires sans créneau régulier n'ont envoyé aucune entrée.
Ces coûts de calibration sont distincts du résultat du mode automatique.

L'analyse a aussi identifié un biais du repère jaune près de la main. Le suivi
peut encore prendre la fléchette tenue pendant l'animation pour un projectile en
vol. L'ajustement exclut désormais les 200 premiers pixels horizontaux depuis le
pivot, correspondant à la zone du lanceur ; ce filtre s'applique à toutes les
trajectoires, sans exclusion sélective de résidus. Au moins huit points et 300 px
de portée restent obligatoires après filtrage. Une régression synthétique avec
points d'animation erronés vérifie que l'angle de vol reste correctement mesuré.
L'essai d'un autre modèle de courbure n'a pas amélioré l'ajustement et n'est pas livré.

Modèle diagonal final : six impacts (dont deux gris), distances 1357,04–1559,04 px,
angles -4,43–35,87 degrés, gain 1,012079, courbure 0,000221795. Erreur maximale en
laissant chaque impact de côté : **22,20 px**, marge inchangée selon la formule
1,5 × erreur + 5 = **38,30 px**. Elle tient dans la demi-hauteur rouge mesurée de
43,5 px. Le maintien demandé reste 1 ms et le délai empirique 20 ms.

Un nouveau `auto-test`, hors données d'ajustement, a fait **50 → 55 (+5, centre)**.
Le pivot courant était (964,96 ; 683,73). Les sondes avaient notamment suivi les
pivots (878,96 ; 738,73), (848,96 ; 713,73), (815,96 ; 567,73) et
(762,96 ; 857,73), en coordonnées ROI. Le vent est ensuite passé à 5 mph dans la
même direction : un nouvel essai a refusé de cliquer (`wind-unknown`).
État final : score 55, deux vies, aucun tir en attente, aucun mode automatique actif.
Un seul tir automatique diagonal de validation ne prouve pas un taux de réussite.

Le modèle privé actif combine les contextes None, droite 6 mph (coefficients de
la passe précédente conservés) et bas-droite 3 mph. Les autres vents restent hors
couverture. Les images et modèles mesurés restent hors dépôt. Suite : 90 tests,
88 réussis, 2 ignorés (droits de liens symboliques Windows).

## Dernier résultat : déclenchement et vent variable

Score initial de cette passe : 36, deux vies. Un diagnostic à maintien de 200 ms,
avec capture concurrente pendant le clic, a confirmé le déclenchement après le
relâchement et coûté une vie. Le clic court suivant a donné 36 → 39 (+3).
Un premier modèle compensé a fait 39 → 44 (+5) avec vent à droite de 4 mph.
Le vent est passé à 6 mph : le modèle précédent a refusé toute entrée.

Quatre sondes privées à 6 mph ont fait 44 → 47 → 50 → 53 → 56. Deux impacts
partiellement superposés à d'anciennes fléchettes ont été vérifiés visuellement et
estimés à partir des nouveaux fragments blancs (incertitude d'annotation : 5 px).
Les premières tentatives d'ajustement sur le dernier angle visible du bras étaient
incorrectes : cette pose appartient aussi à l'animation de lancer. Ces modèles
intermédiaires ne doivent pas servir de calibration définitive.

Le repère jaune de la fléchette a été suivi en vol, sur 37 à 42 positions distinctes
par tir, couvrant environ 900 à 1000 px. Les ajustements quadratiques ont des
résidus RMS de 0,51 à 0,80 px. Les angles initiaux déduits de ces trajectoires ont
servi au modèle actif à 6 mph : gain 0,93274, courbure 0,000180589, erreur maximale
en laissant chaque impact de côté 11,20 px, marge heuristique 21,80 px.
Couverture mesurée : distances 1332–1448 px et angles 17,07–29,14 degrés ; extension
horizontale expérimentale limitée à 10 %. Aucune généralisation à une autre
vitesse ou direction n'est déclarée.

La prévision ignore les images du bras répétées et reconstruit son historique après
saut, irrégularité temporelle ou changement de position/vent. Horizon d'attente
limité à 25 ms, maintien demandé 1 ms, correction empirique de déclenchement 20 ms.
Les appels SendInput ont des bornes avant/après ; les temps effectifs de maintien
observés sont plus longs que 1 ms. Le délai de traitement du jeu n'est pas garanti.
La projection à la collision utilise l'abscisse mesurée 2322, soit -31,5 px du
centre rouge visuel. Pour ce modèle unidimensionnel, le contrôle utilise la hauteur
rouge mesurée de 87 px, avec alignement horizontal imposé ; le mode radial reste
disponible pour les anciens modèles. Les marges sont heuristiques, pas probabilistes.

Deux essais `auto-test` indépendants de l'ajustement ont fait **56 → 61 (+5), puis
61 → 64 (+3)**. Le pivot suivi est passé de (828,96 ; 771,73) à (863,96 ; 849,73),
en coordonnées ROI. Les confirmations proviennent du score observé, pas d'un
classificateur automatique. La deuxième réussite est hors centre : le modèle et
le timing restent expérimentaux. Le vent a alors tourné en bas à droite à 6 mph ;
un nouveau test a refusé de cliquer. Score final 64, une vie, aucun tir en attente.
Le mode continu reste réservé. Aucune remise à zéro nécessaire pour cette passe.

Suite finale : 90 tests, 88 réussis, 2 ignorés (liens symboliques Windows).
Profils, images, trajectoires et rapports restent hors dépôt dans le dossier privé.
Les sections suivantes conservent l'historique des mesures précédentes.

## Première validation de la capture Windows

Essai sur la machine Windows du joueur, écran principal 3440 × 1440, Python
3.12, MSS 10.1.0. Fenêtre Steam Idleon au premier plan, Throwy Darts affiché avant
le premier tir, bras animé, score 0 et vent None. Aucun tir ni calibration effectué.
La compétence computer-use a servi à observer et ajuster la fenêtre ; la mesure
utilise bien WindowsFrameSource/MSS, pas le flux de captures de cette compétence.

## Géométrie et image

Le premier diagnostic a refusé la fenêtre : rectangle client (-8, -8, 3456, 1408)
débordant l'écran. La lecture DWM confirmait des limites débordantes ; aucune
tolérance hors écran n'a été ajoutée au garde. Un double-clic sur la barre de titre
a ramené la fenêtre dans l'écran : rectangle (0, 0, 3440, 1392), DPI de fenêtre 96.
Le contexte peut devoir être recalibré après ce changement de géométrie.

Une image MSS a été vérifiée visuellement : elle montre le mini-jeu, le personnage,
le bras, le vent et le panneau de score, avec des couleurs correctes ; aucune image
noire ni fenêtre étrangère sur cet échantillon. La barre de titre dessinée par le
jeu fait partie de sa zone cliente. Aucun repère de calibration n'est encore choisi.
Les pixels de début et de fin diffèrent dans les deux séries de 300 images.

L'image témoin et le JSON de la série finale restent hors dépôt, dans
`../local/darts-capture-check/`. Aucune capture privée n'est distribuée.

## Débit mesuré

Capture en boucle sans limitation de cadence, images BGR en mémoire. Les gardes,
la conversion BGRA vers BGR, la construction des frames et la collecte des durées
sont inclus dans le débit mural. Pas d'encodage PNG, écriture disque, détection
visuelle, prédiction ni aperçu dans la boucle chronométrée. Quinze captures de
chauffe ont précédé les deux séries de 300 ; la série finale suit une capture témoin.

| Série complète | Images | Durée totale | Débit mural | Capture moyenne | P95 | Maximum | >100 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 300 | 15,168 s | 19,78 im/s | 47,37 ms | 53,29 ms | 72,97 ms | 0 |
| 2 | 300 | 15,389 s | 19,49 im/s | 48,15 ms | 53,91 ms | 75,38 ms | 0 |
| Reprise | 150 | 7,632 s | 19,65 im/s | 47,89 ms | 51,56 ms | 64,87 ms | 0 |

Une troisième série prévue de 300 a été interrompue par le garde de focus/visibilité.
Ses images partielles sont exclues du tableau. Le message ne distingue pas ces deux
causes ; aucun diagnostic plus fin n'a été conservé à cet instant. Après remise du
jeu au premier plan, la reprise de 150 captures s'est achevée. L'interruption n'a
entraîné aucune entrée dans le jeu.

Un essai préliminaire `capture-check --frames 300 --delay 0` a aussi réussi :
moyenne 47,98 ms, minimum 39,07 ms, maximum 67,03 ms. Il n'avait pas encore la mesure
du débit mural. Le diagnostic affiche désormais durée totale, débit mural, P95 et
nombre de captures dépassant 100 ms, avec couverture de ces champs par test.

## Conclusion et limites

La capture du contenu Idleon est vérifiée à cette géométrie, à environ 19,6 im/s.
L'objectif de 60 im/s n'est pas atteint sur la fenêtre entière. Ce débit mesure
les copies d'écran, pas le nombre d'images distinctes rendues par le jeu. Une
zone plus petite ou une optimisation devra être mesurée avant de viser 60 im/s.
Le débit après ajout de la détection reste inconnu ; aucun timing de tir ni latence
d'entrée n'est validé. Aucune conclusion sur les critères SC-001 à SC-005.

Régression après ajout des métriques CLI : 60 tests exécutés, 58 réussis, 2 ignorés
faute de droits de création de liens symboliques. `git diff --check` sans erreur.

## Optimisation DirectX — résultat actuel

Le profilage de 70 acquisitions après 10 tours de chauffe a montré les coûts moyens
suivants à la même résolution : garde Windows 0,08 ms, capture MSS 29,77 ms, copie
BGRA 2,60 ms, conversion Python BGR 14,94 ms. Une conversion OpenCV expérimentale
réduisait ce dernier coût à 3,86 ms, sans permettre 60 im/s à cause de MSS. OpenCV
n'a donc pas été ajouté comme dépendance de capture.

Le backend par défaut est désormais DXGI via DXcam 0.3.0, avec son processeur
NumPy compilé et sortie BGR directe. NumPy 2.5.4 et comtypes 1.5.0 sont les versions
installées et figées dans l'extra capture. MSS reste sélectionnable explicitement.
L'environnement propre au dépôt est `.venv/` ; l'environnement du projet pêche
n'a pas été modifié pour installer DXcam.

L'adaptateur utilise `grab(copy=False, new_frame_only=True)`, sans thread de capture,
sans ring buffer actif et sans mode vidéo à duplication d'images. Le tampon temporaire
est copié une seule fois en octets BGR immuables avant l'acquisition suivante. Les
absences de nouvelle image ne sont pas comptées ; la source attend avec des pauses
de 1 ms et garde le contrôle de focus/visibilité/géométrie/DPI. Elle refuse de
continuer après environ 100 ms sans nouvelle image. Les gardes avant/après acquisition
et l'invalidation persistante de géométrie sont conservés.

### Mesure finale sur Idleon

Même fenêtre entière 3440 × 1392, DPI de fenêtre 96, scène d'attente Throwy Darts
avec bras animé. Aucun recadrage ni réduction de résolution, aucun tir ni calibration.
Vingt acquisitions de chauffe, puis trois séries de 300 avec la classe de production.
Tous les contrôles sont actifs. Écriture PNG et calcul des empreintes hors boucle
chronométrée. L'image DXGI a été inspectée : jeu et couleurs corrects, sans image noire.
Les pixels de début et de fin diffèrent dans chacune des trois séries.

| Série DXGI | Images | Durée totale | Débit mural | Capture moyenne | P95 | Maximum | >16,67 ms | >100 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 300 | 3,021 s | 99,31 im/s | 9,62 ms | 10,56 ms | 20,35 ms | 4 | 0 |
| 2 | 300 | 3,029 s | 99,05 im/s | 9,65 ms | 10,70 ms | 23,37 ms | 2 | 0 |
| 3 | 300 | 3,005 s | 99,82 im/s | 9,57 ms | 10,45 ms | 12,86 ms | 0 | 0 |

Commande publique vérifiée ensuite sur 300 acquisitions supplémentaires :

```powershell
.\.venv\Scripts\python.exe -m idleon_darts capture-check --window-id 10489658 --frames 300 --backend dxgi --delay 0
```

Résultat : 99,15 im/s en 3,026 s, moyenne 9,64 ms, P95 10,48 ms, maximum 35,60 ms,
aucune capture >100 ms. Le HWND est celui de cet essai et doit être recherché à
nouveau pour une autre session. Le JSON du diagnostic inclut backend et le nombre
de captures dépassant le budget de 1000/60 ms.

Les données locales du benchmark sont dans `../local/darts-capture-check/benchmark-dxgi.json`
et l'image témoin dans `dxgi-check.png`, hors dépôt.

**Conclusion actuelle : l'objectif moyen de 60 acquisitions/s est dépassé dans
cette scène à cette résolution, avec environ 99 acquisitions/s (gain proche de ×5).**
Ce n'est pas une garantie de respecter 16,67 ms pour chaque image : 6 captures sur
900 dépassaient ce budget. Le nombre de nouvelles surfaces DXGI n'est pas une mesure
des images distinctes du moteur du jeu ; d'autres animations du bureau peuvent aussi
produire une nouvelle surface. Ces essais courts ne prouvent pas une cadence garantie
sur toutes les scènes ou machines. Le débit avec perception et prédiction reste à
mesurer. Calibration, latence d'entrée et réussite des tirs restent non validées.

Régression finale : 64 tests exécutés, 62 réussis et 2 ignorés faute de droits de
création de liens symboliques. Les nouveaux tests couvrent attente bornée de nouvelle
image, focus pendant l'attente, copie indépendante du tampon DXGI, format des pixels,
refus d'une caméra déjà en capture continue et sélection du backend CLI.

## Calibration visuelle et lancers supervisés — état suivant

L'affichage est resté en 3440 × 1392, DPI de fenêtre 96. La ROI privée choisie
couvre le mini-jeu (2440 × 1360). Les coordonnées personnelles, références et captures
restent dans `../local/darts-calibration/`, hors dépôt. Aucune constante physique
du jeu n'a été ajoutée à partir d'une supposition.

Le nouveau calibrage colour-pca-v1 ajuste les droites de la lame claire sur
360 images, avec une étendue de -19,07 à 56,86 degrés. Le P95 de distance au pivot
est 2,24 px, maximum 3,17 px. Le panneau rouge détecté fait 49 × 87 px ; le rayon
publié est celui d'un cercle conservateur inscrit. Le profil conserve modèle nul
et couverture de tir vide. Les régions et la référence None ont été vérifiées
visuellement ; les seuils de segmentation et de comparaison sont configurés pour
cette apparence, sans garantie pour d'autres équipements.

Sur 600 nouvelles images de contrôle, angle, pivot, cible et vent None sont
disponibles sur 600, direction sur 563. Les 37 abstentions concernent le démarrage
ou une variation insuffisante de l'angle dans l'historique. Débit du contrôle avec
perception : 70,30 im/s. Un modèle de plateforme permet ensuite de mesurer les
translations du personnage, sans garder sa position initiale comme détection.
Après les lancers, un contrôle sur 120 nouvelles images retrouve les quatre
repères sur 120 et la direction sur 114, à 63,95 im/s. Les comptes indiquent la
disponibilité, pas la justesse : ce n'est pas l'évaluation annotée SC-001.

### Lancers et résultats observés

Les clics ont été envoyés par la compétence computer-use, sous supervision de
l'agent. Un collecteur temporaire privé, séparé du produit, a capturé les images
et écouté les événements réels de pression/relâchement. Les contrôles calib/check
du produit restent strictement sans entrée. Aucun adaptateur d'entrée automatique
n'est encore livré dans le solveur.

| Enregistrement | Score avant → après | Résultat visuellement confirmé | Délai repère → pression |
| --- | --- | --- | ---: |
| trial-002 | 0 → 0, avant la partie | Miss au-dessus du panneau | non mesuré |
| trial-004 | 0 → 2 | Impact jaune, démarrage de la partie | 223,89 ms |
| trial-005 | 2 → 5 | Impact vert inférieur, +3 | 221,80 ms |
| trial-006 | 5 → 5 | Miss trop bas, une vie perdue | 965,31 ms |
| trial-007 | 5 → 8 | Impact vert supérieur, +3 | 114,64 ms |
| trial-008 | 8 → 13 | Impact rouge, +5, premier bullseye | 122,16 ms |

État final observé : score 13, deux vies restantes, vent None. Deux autres clics
avant le démarrage n'ont pas d'enregistrement associé : trial-001 était déjà clos
lors de son clic, trial-003 avait refusé la capture avant son clic. Ils ne sont
pas appariés à des images ou événements inventés. Les six enregistrements utiles
ci-dessus sont complets, sans image abandonnée ; trial-001 avait des abandons et
reste exclu de cette série. Les annotations manuelles sont dans calibration-shots.json.

Le premier dispositif d'attente avait un aller-retour entre le repère et le clic.
Le retard de 965 ms montre qu'il ne peut être compensé par une constante universelle.
L'attente et le clic ont ensuite été réunis dans le même appel computer-use ; deux
mesures ont donné 114,64 et 122,16 ms. Ces chiffres caractérisent cet outil de test,
pas un futur adaptateur Win32 du solveur, ni le délai de traitement interne du jeu.

Les pressions ont duré environ 18 ms. Elles ne permettent pas de distinguer un
déclenchement à la pression d'un déclenchement au relâchement : FR-005 reste ouvert.
Une trajectoire a été ajustée à titre exploratoire sur 17 positions de lame de
trial-004, sans validation indépendante ni modèle activé. L'estimation du bout de
la lame visible ne doit pas être confondue avec une coordonnée de collision du jeu.

Un seul bullseye confirmé ne valide ni un taux de réussite, ni une série de neuf,
ni les vents non nuls. Le modèle de trajectoire, la classification automatique des
résultats, 20 tirs annotés puis les évaluations SC-001–005 restent à réaliser.
Les parties automatisées du produit restent indisponibles.

Régression : 75 tests exécutés, 73 réussis, 2 ignorés faute de droits de création
de liens symboliques. Les nouvelles vérifications synthétiques couvrent ajustement
du pivot, ambiguïtés, vent illisible distinct du vent nul, déplacements du personnage,
occultation de la cible, géométrie/DPI incompatibles, sorties privées et absence d'entrée.
# Essais réels du 13 novembre 2026 : modèle et entrées

Essais privés dans Idleon, fenêtre 3440 × 1392, DPI 96. Deux tirs du mode
`auto-test` sans vent ont fait 13 → 18 (centre), puis 18 → 21 (+3). Le second
utilisait un balayage montant ; le prédicteur a ensuite été restreint au sens
descendant couvert par les mesures. Ce petit échantillon ne mesure pas un taux
de réussite. Chaque résultat a été observé et confirmé avant le tir suivant.

Vent suivant : 4 mph à droite, référence comprenant vitesse et flèche. Quatre
sondes de calibration ont fait 21 → 23 → 28 → 31 → 36, toujours deux vies.
Une tentative supplémentaire sans repère de plateforme reconnu n'a pas cliqué.
Le repère a été recadré pour exclure les pieds animés, sans abaisser son seuil.
La reconnaissance du vent ne suffit pas à valider sa trajectoire : le modèle
ajusté a une erreur maximale de validation croisée de 125,47 px, soit une marge
heuristique de 193,21 px pour un rayon cible de 24,5 px. Le test automatique
avec ce vent a refusé le tir, sans entrée et sans réservation non résolue.

Le modèle sans vent utilise quatre impacts antérieurs : erreur maximale de
validation croisée 9,83 px, marge 19,75 px. Les angles sont interpolés autour du
temps de relâchement ; les lacunes d'observation pendant le clic et le véritable
déclenchement press/release restent à caractériser. Aucun seuil n'a été relâché
pour faire accepter le modèle du vent. Aucun succès continu n'est revendiqué.

Suite synthétique/native : 86 tests, 84 réussis, 2 ignorés (droits de création
de liens symboliques Windows). Vérifications : vents inconnus et ambigus,
prévision descendante, absence d'entrée sans armement, arrêt F8, perte de focus,
bouton relâché après erreur et refus des créneaux expirés. Médias et modèles
mesurés restent dans le dossier privé extérieur au dépôt.

# Réanalyse et essais réels du 14 novembre 2026

L'analyse distingue l'orientation de la fléchette tenue en main (champ historique
`arm_angle`) de la direction initiale estimée sur sa trajectoire. Les ajustements
spatiaux donnent de petites erreurs alors que la chaîne affichage/entrée/vol
conserve un déphasage et une dispersion supplémentaires. Un délai uniforme de
20 ms ne caractérise donc pas tous les contextes observés.

L'équation d'impact est désormais inversée analytiquement en `tan(angle)` ; les
racines restent limitées au domaine calibré et l'arc bas est choisi en priorité.
Le prédicteur accepte une correction de phase par contexte, avec une marge
complète obligatoire. Une correction positive retarde la commande. Elle ne
prouve ni une latence interne du jeu ni son déclenchement press/release.
Une pose répétée n'est ni retimestampée ni utilisée pour déclencher ; l'historique
des poses distinctes est conservé sur une répétition brève, puis invalidé après
un blocage prolongé, un saut, une inversion ou un changement de scène.

| Série expérimentale supervisée | Résultat | Usage des mesures |
| --- | --- | --- |
| Sans vent, correction +45 ms figée | 5 rouges sur 5 | Exclus de l'ajustement de cette correction |
| Bas-droite 4 mph, quatre tirs | 3 rouges, 1 vert inférieur | Calibration adaptative du nouveau contexte |
| Bas-droite 4 mph, modèle figé, correction +15 ms | 1 rouge sur 1 | Tir hors ajustement, non réutilisé |

Les positions ont été remesurées avant chaque lancer. Le déplacement vertical
sans vent atteint 194 px. Pour le tir hors ajustement à 4 mph, la pointe a été
mesurée vers y=735, contre un centre à 736,5 px (annotation visuelle, environ
2 px d'incertitude). Score final observé : 61, cinq vies ; aucune vie perdue et
deux gagnées pendant les dix tirs enregistrés. Un tir de démarrage non
chronométré (+3), survenu pendant le recadrage, est exclu et consigné séparément.
Le total 9/10 mélange calibration et essais : ce n'est pas une estimation
indépendante de fiabilité. L'ancienne série de 20 n'a pas été achevée : sept tirs,
trois rouges, puis réutilisation explicitement consignée pour la réanalyse.

Le nouveau modèle 4 mph utilise quatre trajectoires : erreur spatiale maximale
LOO 5,25 px, mais erreur de bout en bout LOO 40,49 px et marge heuristique
65,74 px. Les marges None et diagonale 3 mph restent respectivement 84,69 et
66,90 px. Elles dépassent toutes la demi-hauteur rouge mesurée de 43,5 px.
Trois essais réels du **mode produit** ont donc refusé sans entrée : None
(dispersion), changement None → diagonale 4 mph encore inconnue, puis contexte
4 mph ajusté (dispersion). Les tirs ci-dessus utilisent une sonde expérimentale
de calibration à un seul lancer ; ils ne valident pas l'activation du mode continu.
Aucun seuil produit n'a été abaissé. Aucun modèle continu de toutes les vitesses
et directions du vent n'est démontré. Le contexte droite 6 mph a été exclu du
candidat de phase faute de quatre historiques de prévision exploitables.

Régression : 93 tests exécutés, 91 réussis et 2 ignorés faute de droits de liens
symboliques. Couverture ajoutée : inversion sur deux arcs, cible inaccessible,
limites angulaires, phase positive, marge complète, schéma de correction,
poses répétées sans retimestampage et expiration de leur historique. Les scripts,
modèles, médias et rapports de mesures restent hors du dépôt.

# Déclenchement avec accélération, 14 novembre 2026

Le modèle v2 utilise désormais une politique de prévision conditionnelle. Dix
poses distinctes sont conservées sur au plus 300 ms. Un ajustement quadratique
est ancré sur le dernier angle mesuré : `theta(t)=theta_mesuree+omega*t+alpha*t²/2`.
L'accélération doit dépasser deux fois l'écart-type estimé de son ajustement,
rester bornée à 20 rad/s² et expliquer deux poses retenues hors d'un ajustement
séparé mieux qu'une vitesse constante. Le résidu autorisé reste 0,3°. Ce contrôle
est heuristique : les erreurs de rendu sont corrélées. Si l'accélération n'est pas
étayée, une vitesse locale stable sur six poses est utilisée ; sinon aucun tir.
Le passage à l'angle de visée est résolu sur la branche descendante, à moins de
100 ms de la dernière pose. Le clic doit rester dans les 25 ms à venir et avant
toute inversion prévue, même après correction de phase. Position, cible et vent
différents invalident l'historique. Le modèle historique v1 reste linéaire.

Les premiers ajustements quadratiques courts amplifiaient le bruit ; ils ont été
écartés. Le diagnostic exploratoire final compare 308 poses futures capturées :
erreur moyenne absolue 0,3398° pour la vitesse locale, 0,3381° pour la politique
conditionnelle ; 95e percentile inchangé à 1,5952°. L'accélération non nulle a été
retenue pour 63 comparaisons. Les fenêtres se recouvrent et ont servi aux choix
de conception : ces chiffres ne démontrent ni un gain statistiquement établi,
ni une fiabilité indépendante des tirs. Ils remplacent les chiffres intermédiaires
mesurés pendant la sélection des réglages.

Essai réel dans la partie précédemment laissée à 61 points : une tentative
strictement quadratique n'a pas cliqué. La politique conditionnelle a ensuite
tiré à la nouvelle position (992,96 ; 544,73), en diagonale 4 mph : rouge, score
61 → 66, cinq vies conservées, pointe estimée y=761 contre centre 736,5. Ce tir
expérimental étendait le domaine angulaire de calibration : angle visé 10,09°,
contre minimum appris 13,78°. Cette extension n'est pas activée dans le produit.
Le journal indique **alpha=0** : la vitesse locale a été utilisée, et ce résultat
ne valide donc pas un déclenchement réel avec accélération non nulle.

Après ce tir, le vent est passé à 6 mph en diagonale bas-droite. Le produit a
refusé sans entrée quand le vent était inconnu, puis quand il était reconnu mais
sans trajectoire calibrée. Deux essais de calibration de 15 secondes chacun,
exigeant une accélération validée non nulle, n'ont envoyé aucun clic. Le cas
voisin n'a servi qu'à une amorce de calibration non distribuée, jamais de
substitution de modèle dans le produit. Score final : 66, cinq vies, vent diagonal
6 mph ; zéro vie perdue pendant cette révision. Aucun nouveau point n'a été
réutilisé dans le modèle figé. Les corrections de phase existantes n'ont pas
encore été recalibrées pour la nouvelle prévision.

Régression : 95 tests, 93 réussis et 2 ignorés faute de droits de liens symboliques.
Les nouveaux cas couvrent accélération connue, croisement quadratique, repli sur
vitesse en présence de bruit, remise à zéro au changement de vent et refus d'un
clic repoussé après inversion. Aucun tir réel avec alpha non nul ni mode continu
fiable n'est revendiqué. Les rapports distinguent la politique et le choix effectif.

# Séries automatiques et export pour analyse, 14 novembre 2026

L’application v0.4 permet des séries entièrement automatiques : nombre de tirs
configurable (20 par défaut), 0 pour une boucle sans limite, arrêt F8 ou bouton.
Les résultats sont lus sur le score avant de poursuivre. Une lecture ambiguë
suspend la série et garde le résultat à confirmer. Le vent est lu comme un vecteur,
la position est relocalisée et la visée physique est recalculée pour chaque tir.

Une série réelle de 20 tirs à 1024 × 720 a donné 8 rouges, 12 autres zones et
aucune vie perdue, score 44 → 125. Plusieurs vents diagonaux ont changé pendant
la série. L’ajustement expérimental du délai était actif : ce lot ne valide pas
un modèle figé et démontre 40 % de rouges sur cette collecte, pas 90 %.

Après ajout de la collecte, un test à 3440 × 1392 a enchaîné deux lancers sans
clic manuel, score 0 → 3 → 6, trois vies conservées. Les deux impacts étaient
hors rouge. Les rapports contiennent 38 puis 37 images de vol horodatées,
les observations, les positions, le vent, les reçus natifs et les images avant/après.
Le rendu du jeu était lent : les poses distinctes étaient espacées d’environ
150 ms malgré des captures plus fréquentes. L’historique physique accepte ce
cas et ne redonne pas une nouvelle date aux poses identiques. Le résultat est
attendu jusqu’à 30 s plutôt que de confondre un projectile encore en vol avec un raté.

La prévision harmonique utilise maintenant la phase ajustée sur plusieurs poses.
Cette révision n’a pas démontré de gain de précision indépendant. Le délai est
figé par défaut dans les nouvelles collectes ; l’option CLI `--adapt-timing`
permet explicitement de l’ajuster pendant une série.

L’export local ZIP comprend CSV, JSON, paramètres et captures disponibles, avec
index des fichiers et empreintes SHA-256. L’archive réelle des deux tirs a été
vérifiée : 94 fichiers de données, dont 75 images de vol ; intégrité ZIP et
empreintes correctes. Aucun code ou paquet d’assets du jeu n’est exporté.
La collecte de vol est limitée à 48 images réduites par tir et 80 Mo en mémoire.
Les captures privées restent hors du dépôt. Aucun mode manuel n’est proposé.

Vérification : 114 tests au total ; 111 passent dans le sandbox et trois sont
ignorés. Le test de l’interface Tk ignoré dans le sandbox passe ensuite hors
sandbox, sans entrée dans Idleon. Les deux autres ignorés concernent les liens
symboliques Windows. L’archive source a été construite sans données privées.

# Ajustement des trajectoires et horloge angulaire, 14 novembre 2026

Les 20 tirs supplémentaires de référence ont donné 13 rouges (65 %), sans vie perdue.
La pointe blanche du projectile a été mesurée dans leurs captures de vol.
L'ajustement de l'origine sur les 15 premiers tirs donne une correction de
+24,40 px horizontalement et -7,84 px verticalement, pour une erreur de trajectoire
d'environ 0,81 px. L'ajustement diagnostique sur les 20 donne +24,23 et -7,82 px.
Les cinq derniers tirs n'ont pas remplacé les paramètres retenus.

La politique `phase-clock-v2` estime une phase à partir d'au moins six poses
distinctes sur les deux branches du sinus, avec une horloge calibrée à
1,139721 rad/s avant application du facteur de vitesse du jeu. Elle n'autorise
le lancer que sur la branche descendante. L'attente future est limitée à 45 ms,
et le délai passe de 38 à 31,50 ms. La médiane capture-relâchement observée est
62,7 ms, contre des prévisions souvent proches de 200 ms auparavant.

Le nouveau test réel de 20 tirs donne **16 rouges (80 %), 4 autres zones et zéro
vie perdue**, score 106 → 238. La plus longue séquence est de 11 rouges.
Les changements de position et les vents, dont 12 mph, ont été pris en compte.
Les 90 % ne sont pas atteints et une fiabilité illimitée n'est pas démontrée.

Les coefficients physiques et de timing sont restés figés. Deux défauts
opérationnels ont été corrigés pendant le test et sont consignés dans la session :
lecture de la police violette du vent après le 8e tir, puis recherche des deux
arcs de tir après le 15e. L'ancien encadrement par les extrémités pouvait déclarer
une cible éloignée inaccessible alors qu'un arc intermédiaire la touchait.
Ces changements n'ont pas réajusté les poids du modèle à partir des résultats.
Les tests ajoutés couvrent l'horloge, les poses répétées, les deux arcs éloignés
et le masque des caractères du vent. Captures, ajustements et rapports restent
hors dépôt ; le ZIP d'analyse inclut le rapport de calibration et les reçus natifs.

# Déclenchement sur les crans du bras, 14 novembre 2026

L'analyse des quatre tirs hors rouge de la série précédente (4, 7, 19 et 20)
retrouve des écarts verticaux de +58,5, -76,5, +56,5 et -72,5 px. Les trajectoires
reconstituées ont des erreurs RMS de 0,63 à 0,75 px ; les erreurs angulaires
correspondent plutôt à environ un cran du bras, avec des décalages de +17,4,
-25,2, +14,2 et -21,4 ms. Ces quatre cas étaient sans vent.

La politique `phase-ticks-v3` ajuste une grille de poses et sa cadence locale,
au lieu de supposer un mouvement continu entre deux mises à jour du jeu.
Elle vise le milieu d'une fenêtre de crans dont les impacts calculés restent
dans le rouge avec une marge de trois pixels logiques. Elle privilégie deux
crans consécutifs ; un seul exige une incertitude d'horloge au plus 3 ms. Une pose répétée
ne devient pas une nouvelle mesure de mouvement.

Les données précédentes fixent une correction angulaire de +0,1769 degré et
un délai de 1,5767 période de mise à jour mesurée, soit environ 31,5 ms à 20 ms
par période. La cadence est observée à chaque tir ; ce facteur de délai reste
figé pendant la nouvelle validation. La position et le vecteur du vent sont
relocalisés ; l'amplitude suit la loi du jeu après chaque impact réussi.
La collecte adapte sa durée au temps de vol estimé, avec au plus 48 images.

Régression avant validation réelle : 119 tests, 117 réussis et deux ignorés
pour les liens symboliques Windows. Les nouveaux cas vérifient les fenêtres
de crans rouges et la variation déterministe du délai avec la cadence.

Le test suivant contient **20 nouveaux tirs automatiques : 9 rouges (45 %),
11 autres zones, zéro vie perdue**, score 238 → 321. Il couvre 20 positions de
lanceur et quatre vecteurs de vent distincts, dont deux diagonales successives.
Les 20 reçus natifs sont uniques et 738 images de vol sont disponibles.
Les cinq fenêtres de deux crans ont donné quatre rouges ; les quinze fenêtres
d'un cran ont donné cinq rouges. Ces sous-groupes ne constituent pas une
comparaison contrôlée, car positions et vents diffèrent.

Après cinq tirs, l'attente obligatoire de deux crans a été corrigée : une
oscillation ultérieure ne garantit pas une autre grille de poses. Les coefficients
calibrés sont restés figés, mais ce lot comprend deux versions de cette règle.
Le retard médian du bouton enfoncé par rapport à l'ordre prévu est de 9,08 ms,
avec un maximum de 11,94 ms ; sa contribution aux écarts reste à isoler.
La variante régresse et n'est pas promue. Les préférences conservent les
coefficients v2, avec l'amplitude mise à jour selon les impacts observés.
Le taux précédent de 80 % n'est pas une nouvelle mesure de ce modèle après
ce retour. Les 90 % ne sont toujours pas démontrés. La régression complète
après la correction d'attente reste à 117 tests réussis et deux ignorés sur 119.

# Retour au modèle v2 et budget d'entrée, 14 novembre 2026

Les onze vols hors rouge de la variante par crans ont été reconstruits : dix
correspondent à un déclenchement tardif et un à un déclenchement précoce sur la
branche descendante. Les erreurs RMS de trajectoire vont de 0,41 à 1,17 px.
Les erreurs verticales calculées correspondent aux pointes visibles lorsqu'elles
sont mesurables. La régression concerne donc principalement le déclenchement,
sans nouvelle preuve d'une erreur dans les équations de vent ou de position.
Les estimations de phase de la variante par crans passaient aussi des cas que
les seuils plus stricts de v2 auraient refusés. Ces observations ne permettent
pas d'attribuer tous les écarts à une seule cause.

La nouvelle configuration rétablit les équations, le filtre de phase, ses seuils
et l'absence de biais angulaire du modèle v2. Le délai après relâchement est
recalculé à 24,502701 ms sur les 18 vols v2 exploitables de la série précédente.
Deux vols sont exclus : trajectoire trop bruitée et nombre de points insuffisant.
Le budget d'entrée est mesuré séparément sur les 20 tirs de la régression :
8,625750 ms au-delà de la milliseconde de maintien demandée. Le planificateur
avance l'appel natif de ce budget avant le relâchement prévu. Les horaires
avant/après SendInput ne sont pas présentés comme l'instant exact de réception
par le jeu. Le délai et le budget ne sont pas réajustés pendant la validation.

La partie a été trouvée sur l'écran de départ, score 0. La préparation utilisant
l'amplitude de la partie précédente n'a envoyé aucun tir ; elle a été arrêtée,
puis l'amplitude a été ramenée à sa valeur initiale de 38 degrés avant une série
distincte de 20 tirs. Ce changement d'amplitude décrit une nouvelle partie,
pas un réajustement des coefficients de timing sur les résultats du test.

Régression logicielle avant les tirs : 120 tests, 118 réussis et deux ignorés
pour les liens symboliques Windows. Le nouveau cas vérifie que le budget natif
avance l'ordre du montant prévu sans modifier le délai de phase.

Le nouveau test indépendant donne **14 rouges sur 20 (70 %), six autres zones,
aucune vie perdue**, score 0 → 103. Les 20 positions et quatre vecteurs de vent
distincts sont relus avant les tirs. Cinq des six tirs sans vent et neuf des
quatorze tirs avec vent sont rouges. La plus longue séquence est de cinq rouges.
Les 20 reçus natifs sont uniques et 706 images de vol sont disponibles.
L'écart médian entre le relâchement mesuré et l'horaire budgété est de -0,082 ms,
avec un écart absolu maximal de 9,785 ms. La médiane proche de zéro ne certifie
ni chaque échéance de relâchement ni l'instant de traitement par le jeu.

Les paramètres restent figés pendant les 20 tirs. La série repartant à score 0,
la vitesse du bras et la difficulté diffèrent des séries à score élevé ; le passage
de 45 à 70 % ne prouve donc pas à lui seul l'effet causal de la correction.
Le taux de 90 % n'est pas atteint et aucun gain par rapport au lot à 80 % n'est
confirmé. Les préférences conservent les coefficients v2 de référence avec
l'amplitude de la partie courante, sans promouvoir le nouveau réglage à 70 %.
Les résultats et leurs paramètres restent distincts dans l'export, avec index
SHA-256, captures avant/après, vols et rapport des onze écarts précédents.

# Ajustement sur les plages rouges, 14 novembre 2026

Les six tirs hors rouge du lot à 70 % (6, 8, 9, 13, 14 et 20) ont des angles
correspondant à un déclenchement tardif. L'erreur RMS de leurs trajectoires est
de 0,65 à 0,98 px. Les impacts reconstitués sont de 47 à 89 px sous le centre.
La bande rouge est bien considérée dans toute sa hauteur pour le résultat,
avec les bonus de score ; viser le centre sert à maximiser la marge.
La fenêtre native de trois millisecondes ne représente pas une tolérance
de trois pixels à l'impact.

La nouvelle configuration part de la géométrie et du filtre du modèle v2.
Elle calcule des intervalles de délai admissibles à partir des bords rouges,
avec trois pixels logiques de marge près des barres. Dix-sept vols du lot
précédent, rouges et hors rouge, sont exploitables ; deux vols trop bruités
et un ajustement de phase invalide sont exclus. Le délai est choisi au milieu
de leur intersection : 40,595333 ms, avec un budget natif de 7,752650 ms.
L'ordre est ainsi avancé d'environ 15,22 ms par rapport au lot précédent.
Les paramètres, y compris les seuils du filtre v2, sont figés avant les tirs.

Les 17 intervalles d'apprentissage se recouvrent entre 40,247 et 40,944 ms.
Cette couverture calculée n'est pas un taux de réussite mesuré et le plateau
est étroit ; elle ne démontre pas 90 %. Le modèle externe est vérifié par le
chargeur du produit, sans changement du code exécutable. La nouvelle série
commence à score 103 sans remise à zéro et reste distincte du lot de calibration.

Le nouveau test indépendant donne **15 rouges sur 20 (75 %), cinq autres zones,
zéro vie perdue**, score 103 → 213. Les 20 positions et quatre vecteurs de vent
distincts ont été pris en compte. Les sept derniers tirs sont rouges.
Les coefficients restent figés sur les 20 tirs ; l'export contient 20 reçus
natifs uniques et 709 images de vol. L'écart médian du relâchement par rapport
à son budget est de +1,323 ms, avec un écart absolu maximal de 5,814 ms.
Ces horaires Windows ne prouvent pas l'instant de traitement par le jeu.

L'audit des pointes mesurables vérifie leur appartenance à la bande rouge en
complément du score. Les cinq échecs sont tous en dehors de cette bande, quatre
au-dessus et un au-dessous ; des pointes éloignées de plus de 30 px du centre
comptent bien comme rouges. Les 90 % ne sont pas atteints, ni un gain démontré
par rapport au lot à 80 %. Les préférences conservent les coefficients v2 de
référence avec l'amplitude de la partie courante ; ce réglage à 75 % reste
disponible séparément pour analyse, sans être promu.

# Relâchement à échéance absolue, 14 novembre 2026

Les cinq écarts du lot à 75 % (1, 5, 7, 12 et 13) sont quatre tirs précoces et
un tardif. Les trajectoires reconstituées donnent des erreurs RMS de 0,67 à
1,49 px. Une correction appliquée uniquement aux tirs ratés serait donc
insuffisante. Les données de trois séries précédentes sont réunies : 53 vols
exploitables, incluant rouges et hors rouge, sans changer la géométrie ni les
filtres de phase du modèle v2. Le délai retenu est 27,448847 ms. Les couvertures
calculées des intervalles, dont les contrôles avec une série exclue, restent des
diagnostics d'apprentissage et ne sont pas une mesure du nouvel ordonnanceur.

Sur la version installée inspectée, le gestionnaire du lancer est relié à
l'événement de relâchement. L'entrée native prépare maintenant l'appui 30 ms
avant une échéance absolue de relâchement, plutôt que d'ajouter une durée après
le retour de SendInput. L'attente reste gardée par le focus, la géométrie et F8.
Une échéance périmée est refusée avant l'appui ; un appel d'appui trop lent
déclenche une libération immédiate avec une erreur explicite. Le mode ancien
reste celui des modèles ne portant pas `absolute_mouse_up: true`.

La réservation de l'appui admet 10 ms de retard avec le réglage de préparation
à 30 ms ; l'échéance de relâchement reste inchangée. Les reçus stockent
`planned_up_ns`, et le CSV exporte l'écart de relâchement `up_error_ns`.
Les tests simulés conservent la même échéance avec des appels d'appui de 2,
12 et 25 ms, et vérifient échéance expirée, appel trop lent et perte de focus.
Régression avant validation réelle : 123 tests, 121 réussis, deux ignorés pour
les liens symboliques Windows. Le nouveau lot commence au score 213, sans
remise à zéro, avec paramètres figés avant les 20 tirs.

Le test indépendant donne **13 rouges sur 20 (65 %), sept autres zones,
aucune vie perdue**, score 213 → 329, avec 20 positions et quatre vecteurs de
vent distincts. Les 20 reçus natifs contiennent une échéance de relâchement et
ne signalent aucune erreur d'entrée. L'écart médian est de +0,838 ms ; le maximum
absolu est de 1,223 ms, contre 5,814 ms au maximum sur le lot précédent.
La collecte contient 682 images de vol ; la plus longue séquence du lot est
de trois rouges. Aucun tir antérieur n'est inclus dans ces 20 résultats.

Cette mesure améliore la régularité du relâchement Windows mais ne montre
aucun gain du taux de rouges. Le délai de traitement du jeu et l'estimation
de phase restent à distinguer : les horaires d'appel ne prouvent pas l'instant
de prise en compte dans le moteur. Les 90 % ne sont pas atteints et le nouveau
réglage n'est pas promu. Les préférences conservent le modèle v2 de référence,
avec l'amplitude correspondant à la partie courante. La régression finale
reste à 121 tests réussis et deux ignorés sur 123 ; le mode ancien conserve
son attente d'origine pour les modèles sans relâchement absolu.

# Application 0.5 et démarrage rapide, 14 novembre 2026

À la demande de l'utilisateur, l'algorithme à relâchement programmé mesuré à
65 % devient le modèle de l'application. Les nouveaux profils automatiques
reçoivent ses paramètres, avec les corrections d'origine exprimées à l'échelle
du profil. Le profil et le modèle courant sont mémorisés ; le modèle appris est
conservé séparément des captures dans `models/application-current.json`.
Le démarrage nécessite un clic sur Lancer la série, sans chargement manuel ni
case d'autorisation supplémentaire. Sans profil, Préparer et lancer effectue
la calibration puis démarre la série. L'interface ne tire jamais à son ouverture.

La capture Windows et le détecteur sont conservés durant toute la série, sur
le même thread. Les essais sans créneau gardent le même identifiant de mouvement.
Les lectures de score et de vies se poursuivent après le relâchement ; deux
lectures stables espacées d'au moins 50 ms permettent de terminer immédiatement
la collecte, au lieu d'attendre systématiquement 2,5 secondes. Un score inchangé
ne déclenche pas cette sortie anticipée. Les captures et les contrôles de focus,
de géométrie et d'âge restent actifs. F8 est mémorisé même lorsqu'il est reçu
pendant un appui. Une nouvelle partie à score zéro remet l'amplitude à 38 degrés.

La préparation automatique et cinq tirs ont été vérifiés réellement dans Idleon
sur un nouveau profil : score 0 → 30, cinq rouges, aucune vie perdue. Les intervalles
entre relâchements sont 3,74, 7,21, 11,58 et 6,67 secondes ; la recherche du créneau
reste variable. La confirmation après tir est médiane à 1,146 s (1,086 à 1,183 s)
sur ces cinq essais. Ils ne démontrent pas une précision de 100 % à long terme.
La référence de précision reste le lot de 20 à 65 %, avec positions et vents variés.

Régression : 125 tests, 123 réussis et deux ignorés pour les liens symboliques
Windows. Le test de collecte rapide vérifie la sortie après deux scores stables
et l'absence de fermeture de la capture partagée par un essai individuel.
L'interface réelle de l'exécutable a été ouverte et vérifiée ; le bouton Arrêter
reste visible et les contrôles de fenêtre et de nombre de tirs sont lisibles.
