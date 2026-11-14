# Idleon Darts — Windows

Un helper pour lancer automatiquement dans **Throwy Darts**, lire les résultats et enregistrer les données pour les analyser plus tard.

La version 0.6 utilise le modèle à relâchement programmé. Sa précision de référence est **65 % de rouges sur 20 tirs**, sans vie perdue sur ce lot. Les 90 % ne sont pas validés.

## Télécharger la version Windows

**[Télécharger Idleon Darts 0.6.0 pour Windows x64](https://github.com/Akokokih/Idelon_darts/releases/download/v0.6.0/IdleonDarts-0.6.0-Windows-x64.zip)**

Décompresser entièrement le ZIP dans un dossier personnel, puis double-cliquer sur **Lancer.cmd**. Python est inclus : aucune installation Python n'est nécessaire pour cette version.

Conserver le dossier `IdleonDarts` et son sous-dossier `_internal` ensemble. Les données créées à l'utilisation sont enregistrées dans `local/idleon-darts-app`, à côté du lanceur.

## Mode d’emploi

1. Ouvrir Idleon sur Steam et afficher le mini-jeu **Throwy Darts**.
2. Ouvrir **Lancer.cmd** dans la version Windows, ou **Start-Idleon-Darts.cmd** pour l'installation depuis les sources.
3. Choisir le **nombre de tirs** : `20` par défaut, ou `0` pour continuer jusqu’à l’arrêt.
4. Cliquer sur **Lancer**. Au premier démarrage, **Préparer et lancer** effectue automatiquement la calibration.

L’application détecte Idleon et mémorise le profil et le modèle. Elle ne tire pas à son ouverture : il faut cliquer sur Lancer.

**Arrêter** ou **F8** interrompt la série. Les positions et le vent sont relus avant les tirs. Toute la bande rouge compte comme une réussite.

## Récupérer les données

À la fin d’une série, cliquer sur **Exporter**. Le ZIP contient les scores, les timings, les paramètres et les captures disponibles.

L’export reste sur votre ordinateur : aucun fichier n’est envoyé sur GitHub ou à un autre service. Les trajectoires sont enregistrées par défaut.

## Options avancées

Elles sont masquées au démarrage et ne sont pas nécessaires pour jouer normalement.

Utilisez **Options avancées** pour recalibrer après un changement de zoom ou de taille de fenêtre, choisir une autre fenêtre Idleon, charger un modèle, consulter l’aperçu et les journaux, ou confirmer un résultat ambigu.

Si le mini-jeu n’est pas reconnu, affichez Throwy Darts et relancez la préparation. Une lecture de résultat ambiguë suspend les tirs jusqu’à sa confirmation.

## Installer depuis les sources

Prérequis : Windows et Python 3.12, avec Idleon installé via Steam.

1. Télécharger le code du dépôt et le décompresser.
2. Dans PowerShell, depuis le dossier du projet, exécuter `./Install-Idleon-Darts.ps1`.
3. Ouvrir `Start-Idleon-Darts.cmd`.

Depuis les sources, les profils et captures sont conservés hors du code, dans `../local/idleon-darts-app/`. Aucun profil ni aucune capture personnelle n'est fourni dans les archives de distribution.

## Développement et mesures

Tests : `.venv\Scripts\python.exe -m unittest discover -s tests`.

L’[historique des mesures](specs/001-automatic-darts/validation.md) décrit les tests réels et leurs limites. L’[archive technique](specs/001-automatic-darts/advanced-usage.md) conserve les détails du moteur et des commandes avancées.
