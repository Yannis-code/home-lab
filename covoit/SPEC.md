# Application de covoiturage

## Objectif

Créer une application simple pour organiser des trajets de covoiturage au sein de groupes et répartir leurs frais de carburant.

## Acteurs et groupes

- L'application comporte plusieurs utilisateurs.
- Les comptes utilisent une authentification locale et sont créés par l'unique administrateur global de l'application.
- Chaque compte requiert un nom affiché, une adresse e-mail et un mot de passe créé par l'administrateur.
- Le mot de passe initial est temporaire et doit être changé lors de la première connexion.
- En cas de mot de passe oublié, l'administrateur génère un nouveau mot de passe temporaire à changer à la prochaine connexion.
- La désactivation d'un compte conserve le nom de la personne, ses trajets et ses soldes dans l'historique.
- Tout utilisateur peut créer un groupe et en devient le gestionnaire initial.
- Seul le nom de profil est visible aux autres membres d'un groupe; l'adresse e-mail n'est pas affichée.
- Un groupe de covoiturage rassemble plusieurs utilisateurs.
- Un utilisateur peut appartenir à plusieurs groupes.
- Le créateur du groupe invite des comptes utilisateur existants en les sélectionnant dans l'application. Il n'est pas nécessairement conducteur.
- L'adhésion d'une personne invitée ne devient effective qu'après son acceptation.
- Le créateur est gestionnaire du groupe et peut transférer cette gestion.
- Le gestionnaire peut archiver un groupe; le groupe devient inactif et son historique détaillé est conservé en lecture seule pour les membres présents à la date d'archivage.
- L'administrateur global n'obtient pas d'accès aux données d'un groupe du fait de son rôle.
- Un membre peut quitter un groupe de lui-même, sauf s'il en est le dernier gestionnaire.
- Un membre ayant participé aux trajets d'un mois conserve l'accès au bilan de ce mois jusqu'à sa validation, même s'il quitte le groupe.
- Chaque groupe a un conducteur par défaut.
- Tous les membres peuvent changer le conducteur par défaut du groupe.
- Le conducteur par défaut peut être remplacé pour un trajet donné.
- Les autres participants au trajet sont des passagers.
- Tout membre peut créer, modifier ou supprimer les trajets et modèles récurrents du groupe.

## Véhicules

- Chaque utilisateur peut gérer sa propre liste de véhicules.
- Le propriétaire peut autoriser un ou plusieurs groupes à utiliser son véhicule.
- Un véhicule comporte au minimum : nombre de places, marque, modèle et une ou plusieurs sources d'énergie avec leur consommation moyenne.
- La consommation est enregistrée par source d'énergie avec une unité adaptée, par exemple L/100 km ou kWh/100 km.
- Le nombre de places inclut le conducteur.
- Les carburants/énergies visés sont l'essence, le diesel, l'éthanol et l'électricité; un véhicule hybride peut combiner plusieurs sources d'énergie.
- Lorsqu'un utilisateur conduit un trajet, il peut sélectionner un véhicule auquel il a accès parmi ses véhicules ou les véhicules partagés avec lui.

Le périmètre prévu couvre essence, diesel, éthanol et électricité; les véhicules hybrides peuvent consommer plusieurs sources d'énergie.

## Trajets

- Un trajet appartient à un groupe de covoiturage.
- Un trajet peut être ponctuel ou récurrent.
- Un trajet récurrent est défini par un modèle qui génère des occurrences datées.
- Un modèle récurrent génère des occurrences sans date de fin, jusqu'à sa pause ou sa suppression.
- Un modèle récurrent peut être mis en pause puis repris.
- La suppression d'un modèle arrête ses occurrences futures; les occurrences passées et les bilans associés sont conservés.
- Un modèle récurrent permet de choisir les jours de semaine et l'heure; chaque sens a son propre modèle.
- Lorsqu'un modèle récurrent est modifié, le groupe choisit si le changement concerne une seule occurrence ou toute la série.
- Chaque sens de déplacement possède son propre modèle (par exemple domicile-travail le matin et travail-domicile le soir).
- Une occurrence d'un trajet récurrent peut être modifiée ou annulée individuellement, par exemple en cas d'absence.
- Une occurrence est comptabilisée automatiquement à sa date prévue, mais reste modifiable.
- Le modèle récurrent propose la même liste fixe de passagers pour chaque occurrence; une occurrence peut être modifiée individuellement.
- Chaque passager accepte une fois sa présence dans le modèle récurrent avant d'être inscrit par défaut aux occurrences.
- Chaque occurrence peut avoir un statut explicite, notamment prévue, effectuée ou annulée/non effectuée.
- Un trajet représente un ensemble de personnes et un départ ainsi qu'une destination.
- Les informations du trajet sont modifiables par les membres du groupe.
- Le conducteur d'un trajet peut différer du conducteur par défaut du groupe.
- Le conducteur sélectionne un véhicule lui appartenant ou partagé avec le groupe.
- Les utilisateurs participant au trajet sont identifiés comme conducteur ou passagers.
- Les passagers peuvent s'inscrire eux-mêmes à un trajet.
- Une demande de place précise l'arrêt de montée existant ou propose un point de prise en charge.
- L'inscription d'un passager doit être acceptée avant de réserver sa place.
- En cas de refus, la demande est close et le demandeur est notifié.
- La distance parcourue est saisie manuellement.
- Un trajet est détaillé en étapes/tronçons avec les personnes présentes dans le véhicule sur chaque tronçon.
- La distance du détour effectué spécialement pour récupérer une personne est saisie manuellement et attribuée à cette personne.
- Tout membre du groupe peut annuler un trajet ponctuel.
- Les informations d'une occurrence passée restent modifiables jusqu'à la clôture du mois; après clôture, seul le gestionnaire peut apporter une correction tracée.
- Une correction après clôture conserve l'ancienne et la nouvelle valeur, l'auteur, la date et un motif obligatoire; elle entraîne le recalcul ou la réouverture du bilan concerné.
- Les remboursements déjà confirmés restent conservés; tout écart de solde résultant d'une correction est reporté au bilan suivant.
- Le conducteur accepte ou refuse les demandes de place, sans pouvoir dépasser la capacité du véhicule, conducteur inclus.
- Si toutes les places sont prises, les nouvelles demandes peuvent rejoindre une liste d'attente examinée par le conducteur lorsqu'une place se libère.
- Un trajet comporte au minimum une date et heure, un départ, une destination, un conducteur, un véhicule, des passagers et la distance.
- Les lieux de départ, d'arrivée et les arrêts sont sélectionnés à partir d'adresses sur une carte; les distances restent saisies manuellement.
- La cartographie et la recherche d'adresses s'appuient sur les services publics OpenStreetMap, dans le respect de leurs limites et règles d'usage.

## Frais de carburant

- Chaque mois, le propriétaire renseigne le prix des sources d'énergie pour son véhicule, pour permettre le calcul des frais des trajets du groupe.
- Le prix est propre à chaque véhicule, à chaque source d'énergie et saisi mensuellement dans l'unité correspondante (par exemple par litre ou par kWh).
- Un prix unique est utilisé pour le mois et peut être modifié avec effet sur l'ensemble du mois.
- Si un prix manque, le bilan concerné reste incomplet et ne peut pas être clôturé jusqu'à sa saisie.
- Les prix et soldes sont exprimés en euros (EUR).
- Le carburant concerné est celui du véhicule sélectionné pour le trajet.
- Le calcul doit s'appuyer sur le prix du carburant et la consommation moyenne du véhicule.
- Le coût de chaque tronçon est calculé selon sa distance, la consommation et le prix applicable, puis partagé également entre toutes les personnes à bord, conducteur inclus.
- Pour un véhicule utilisant plusieurs sources d'énergie, le coût du tronçon est la somme des coûts calculés pour chacune de ses sources configurées.
- La part totale d'une personne est la somme de ses parts pour les tronçons où elle est présente.
- Le conducteur est inclus dans la répartition et avance le coût total du trajet; il paie sa propre part.
- Seuls les kilomètres supplémentaires du détour par rapport au trajet normal sont comptabilisés comme détour; leur coût carburant est imputé au passager récupéré, sans double comptage dans les tronçons partagés.
- Un bilan mensuel calcule un solde net du groupe et propose des virements entre membres pour réduire le nombre de règlements.
- Les virements proposés sont des suggestions modifiables, pas une obligation.
- Seuls les membres ayant participé à au moins un trajet du mois doivent valider le bilan; un refus bloque la clôture.
- Cette validation reste requise si le membre quitte le groupe avant la clôture.
- Toute occurrence passée encore au statut prévue doit être marquée effectuée ou annulée avant la validation du bilan.
- Un remboursement déclaré par son payeur ne réduit le solde dû qu'après confirmation du bénéficiaire.
- Les membres du groupe peuvent exporter les bilans mensuels au format PDF ou CSV.

## Accès et notifications

- L'application est une PWA installable et s'adapte aux écrans mobiles et ordinateurs.
- L'accueil demande de choisir un groupe avant d'afficher ses trajets et son bilan.
- Hors ligne, la PWA permet uniquement de consulter les données récemment mises en cache; toute modification nécessite une connexion.
- Les trajets, participants et bilans d'un groupe sont visibles uniquement par ses membres; le rôle d'administrateur global ne donne pas accès aux données des groupes.
- Les notifications sont affichées dans l'application, sans envoi d'e-mail.
- Les notifications couvrent les invitations, demandes d'inscription et décisions, changements/annulations de trajets, saisie et validation des bilans, ainsi que les confirmations de remboursement.
- Les rappels à l'approche des trajets et des échéances sont activables ou réglables par utilisateur dans les préférences du compte.

## Questions ouvertes

- Choix du fournisseur concret de cartes et de géocodage compatible avec OpenStreetMap et ses règles d'usage.