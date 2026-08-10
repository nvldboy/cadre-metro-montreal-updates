# Données GTFS du cadre du métro de Montréal

Ce petit dépôt public distribue uniquement l’horaire compact nécessaire au
cadre DEL. Il ne contient aucun mot de passe Wi-Fi, aucune clé API STM et aucun
code de configuration personnel.

Le Raspberry Pi Pico 2 W lit ce manifeste public :

`https://raw.githubusercontent.com/nvldboy/cadre-metro-montreal-updates/main/updates/latest.json`

Le fichier `updates/metro_schedule_data.py` est vérifié par taille et par
empreinte SHA-256 avant son installation. Une automatisation GitHub vérifie le
GTFS officiel de la STM chaque lundi et ne crée un nouveau commit que si
l’horaire a réellement changé.

## Public files

This public, data-only repository contains the compact schedule used by the LED
metro frame. It contains no Wi-Fi password, STM API key, or personal
configuration. GitHub Actions checks the official STM GTFS every Monday and
publishes a new version only when the schedule actually changes.

## Attribution

Les données de transport sources proviennent de la Société de transport de
Montréal (STM) et sont offertes sous licence Creative Commons Attribution 4.0.
Ce projet indépendant n’est ni produit ni approuvé par la STM.

Source data is provided by the Société de transport de Montréal (STM) under
Creative Commons Attribution 4.0. This independent project is not produced or
endorsed by the STM.
