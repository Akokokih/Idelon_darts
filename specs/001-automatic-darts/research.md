# Research — décisions de conception

Date : 2026-11-13. Recherche sur les documentations primaires et consolidation
d’un agent de recherche, conformément à l’étape Spec Kit.

## Capture et conservation

**Decision** : MSS, zone choisie, écran principal ; données de calibration sous forme
d’images PNG sans perte avec index temporel. Le collecteur privé est hors projet.

**Rationale** : les contours fins du bras et de la cible sont importants. Chaque
image conserve son intervalle de capture ; le temps de lecture d’une vidéo à cadence
fixe ne serait pas une mesure fiable du rendu réel. Queue d’écriture bornée ;
compter abandons et créneaux manqués. Aucune prévisualisation continue pendant la capture.

**Alternatives considered** : MJPG/AVI plus compact mais avec perte ; DXGI plus rapide
potentiellement mais plus de complexité ; simple enregistrement sans événements insuffisant
pour rapprocher pression, relâchement et lancer. Réévaluer après mesures du débit.

Sources : [MSS API](https://python-mss.readthedocs.io/stable/api.html),
[MSS 10.1.0, API retenue par le collecteur](https://pypi.org/project/mss/10.1.0/),
[OpenCV VideoWriter](https://docs.opencv.org/4.13.0/dd/d9e/classcv_1_1VideoWriter.html).
La version 10.1.0 est choisie pour son API connue, sans prétendre être la plus récente.

## Horodatage et entrées observées

**Decision** : origine UTC pour identifier la session, `perf_counter_ns` relatif
pour images et événements. Conserver début et fin de capture. Les callbacks ne
font qu’horodater et mettre en file ; traitement et écritures sur d’autres threads.

**Rationale** : éviter une horloge civile qui saute et un blocage du fil d’entrée
Windows. Un timestamp de callback n’est pas le moment exact du traitement dans le jeu.

**Alternatives considered** : cadence nominale seule ou `time.time` pour la chronologie,
insuffisants pour mesurer le timing. Le temps exact du moteur ne sera pas accessible
par la seule observation de l’écran.

Sources : [Python time](https://docs.python.org/3.12/library/time.html),
[pynput et callbacks Windows](https://pynput.readthedocs.io/en/latest/mouse.html).

## Géométrie et DPI

**Decision** : pixels physiques ; conscience DPI avant UI et imports qui fixent le DPI.
Un exécutable futur déclarera le mode dans son manifeste ; le script temporaire le
fixe par API et vérifie qu’un mode par moniteur est actif. Vérifier premier plan et
rectangle avant/après capture ; suspendre si l’un change.

**Rationale** : écran à 125 % ou 150 % peut sinon décaler souris et captures.
La vérification avant/après réduit les captures hors fenêtre mais ne rend pas les
changements de focus atomiques avec une capture de l’écran.

**Alternatives considered** : coordonnées logiques fixes, rejetées ; capture d’une
fenêtre en arrière-plan, hors périmètre initial et support incertain pour le jeu.

Source : [Microsoft SetProcessDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext).

## Prédiction et effet du vent

**Decision** : commencer par un modèle empirique reliant position, angle/direction du
bras et contexte de vent à l’impact ; comparer à un modèle physique ajusté si les
trajectoires visibles permettent de l’identifier. Tester les deux sur des sessions
distinctes, publier erreurs et couverture. Aucun angle fixe universel.

**Rationale** : aucune formule du moteur vérifiée. La similarité d’un sprite seule
ne distingue pas nécessairement la direction du mouvement ni le contexte du lancer.
Prédire l’impact, puis rechercher une fenêtre où l’incertitude reste à l’intérieur
du centre. S’abstenir si cette fenêtre est plus petite que l’incertitude temporelle.

**Alternatives considered** : timer fixe, insuffisant pour les contextes variables ;
reconnaissance d’une unique pose, insuffisante pour la direction et le vent ;
modèle balistique à constantes inventées, non validable.

Les captures serviront à confirmer le déclenchement au relâchement, l’effet du vent,
les déplacements et la latence. Ces résultats restent non mesurés, sans bloquer la
conception de leur protocole de mesure.

## Contrôle et distribution

**Decision** : adaptateur Win32 séparé, préconditions revérifiées juste avant l’entrée,
arrêt prioritaire, bouton relâché à la suspension, aucun double tir. Outil de collecte
à écoute seule, sans contrôleur souris ni saisie de texte.

**Rationale** : le moteur de prédiction doit pouvoir être testé sans agir sur le jeu.
Pas d’exécutable Windows annoncé avant compilation et essai sur Windows.

**Alternatives considered** : bot navigateur et injection dans le jeu, hors besoin.

## Conclusion de recherche

Tous les choix nécessaires au plan ont une décision et une alternative. Le débit,
les erreurs de détection et la physique sont à mesurer pendant l’exécution du plan.
Ils ne sont ni des résultats acquis ni des constantes de configuration préremplies.

## Décision T011 — lecture des captures sans dépendance native supplémentaire

Lecture directe des ZIP par la bibliothèque standard, sans extraction. Le format
RGB8 non entrelacé généré par MSS est décodé et validé avec struct/zlib ; autres
variantes PNG rejetées explicitement. Cela permet de tester le lecteur avant
l’intégration OpenCV de la perception et sans embarquer le collecteur temporaire.
Les filtres 0 à 4, CRC, fins de flux et dimensions sont couverts par des images
synthétiques, dont des lignes à plusieurs pixels pour exercer les voisins gauche/haut.

Sources primaires consultées le 13 novembre 2026 :
[format PNG du W3C](https://www.w3.org/TR/png-3/),
[encodeur MSS 10.1.0](https://raw.githubusercontent.com/BoboTiG/python-mss/v10.1.0/src/mss/tools.py).
Le décodage est limité au format du collecteur, sans prétendre couvrir tout PNG.

## Décision T012 — capture Windows sans calibration

Adaptateur MSS 10.1.0 optionnel, chargé à la demande. La région par défaut est
la zone cliente de la fenêtre explicite, traduite en coordonnées écran physiques
par GetClientRect/ClientToScreen. Cela exclut les bordures invisibles des fenêtres
maximisées. Un contexte DPI par moniteur V2 est appliqué au thread puis restauré,
sans modifier globalement le mode DPI de l'application à l'import.

GetDpiForWindow fournit le DPI de la fenêtre cible (96 si elle n'est pas consciente
du DPI), pas une mesure indépendante du DPI physique du moniteur. Le garde vérifie
identité HWND/PID/thread, focus, visibilité, minimisation, état DWM, géométrie et
écran principal avant/après capture. Il ne garantit pas l'absence de recouvrement
ni la détection d'un aller-retour complet entre deux lectures.

Sources primaires consultées pour cette implémentation :
[GetClientRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclientrect),
[SetThreadDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext),
[GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow),
[implémentation MSS Windows 10.1.0](https://raw.githubusercontent.com/BoboTiG/python-mss/v10.1.0/src/mss/windows.py).
Les tests natifs automatisés ne lisent pas les pixels du bureau. Un essai réel
distinct a confirmé la capture Idleon à environ 19,6 im/s sur 3440 × 1392 ; voir
[validation.md](validation.md). Le verrouillage complet des dépendances reste ouvert.

## Optimisation T012 — DXGI par défaut, MSS en compatibilité

Le profilage MSS à 3440 × 1392 attribue environ 30 ms à l'acquisition et 15 ms
à la conversion Python des canaux ; accélérer uniquement la conversion ne suffit
pas pour viser 60 im/s. Le chemin par défaut utilise donc DXcam 0.3.0 avec backend
DXGI, processeur NumPy compilé et sortie BGR. Une seule copie vers des octets
immuables protège la frame contre la réutilisation du tampon d'acquisition.

La capture reste synchrone et demande `new_frame_only=True`, sans cache vidéo ni
thread de capture. L'absence d'image entraîne une attente bornée avec vérification
du contexte. Les horodatages encadrent acquisition, attente et gardes ; ils ne sont
pas des horodatages de rendu du moteur du jeu. L'API ne fabrique pas une nouvelle
frame à partir d'une image mise en cache.

Sources : [documentation et API DXcam](https://github.com/ra1nty/DXcam),
[distribution DXcam 0.3.0](https://pypi.org/project/dxcam/0.3.0/), ainsi que le code
installé de dxcam.py et core/dxgi_duplicator.py pour cette version. Le chemin DXGI
utilise AcquireNextFrame avec délai nul ; l'attente et le refus après environ
100 ms sont gérés par notre source. Les fichiers DXcam restent une dépendance,
sans copie de leur code dans le solveur.

Les versions de capture sont figées après essai Windows : DXcam 0.3.0, NumPy 2.5.4,
comtypes 1.5.0, MSS 10.1.0. Trois séries de 300 images donnent environ 99 im/s, avec
P95 autour de 10,5 ms ; voir validation.md pour le protocole et ses limites. La
validation future avec détection et modèle de tir reste à effectuer.
