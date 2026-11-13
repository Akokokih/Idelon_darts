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
