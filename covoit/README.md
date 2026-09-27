# Covoit — v1

Application de covoiturage: groupes, trajets (ponctuels et récurrents),
véhicules multi-énergies et bilan mensuel des frais de carburant, avec
solde net simplifié entre membres. Une PWA statique (`web/`) consomme l'API.

Le contexte fonctionnel complet est décrit dans [`SPEC.md`](./SPEC.md). Ce
document précise ce qui est réellement implémenté dans cette v1 et ce qui est
volontairement laissé pour une itération suivante.

## Démarrer

```bash
just sync            # crée .venv/ et installe le projet + dépendances de dev
just serve            # démarre l'API + la PWA sur http://127.0.0.1:8000 (docs API sur /docs)
just test-unit        # tests unitaires (logique pure, sans HTTP/DB)
just test-integration # tests d'intégration (FastAPI + SQLite en mémoire)
just test             # suite complète
```

Depuis la racine du dépôt: `just covoit::sync`, `just covoit::test`, etc.

Au premier démarrage, un compte administrateur est créé automatiquement.
Configurez-le via variables d'environnement (`COVOIT_ADMIN_EMAIL`,
`COVOIT_ADMIN_PASSWORD`); si aucun mot de passe n'est fourni, un mot de passe
temporaire est généré et affiché dans les logs au démarrage.

Variables d'environnement principales: `COVOIT_DATABASE_URL` (défaut
`sqlite:///./covoit.db`), `COVOIT_SESSION_TTL_HOURS`, `COVOIT_ADMIN_NAME`,
`COVOIT_ADMIN_EMAIL`, `COVOIT_ADMIN_PASSWORD`.

## Architecture

- `web/`: PWA statique (HTML/CSS/JS vanille, sans build), servie directement
  par FastAPI (`StaticFiles`, montée après les routes API). Routage par hash
  (`#/groupes/...`), jeton de session en `localStorage`, `manifest.json` +
  `service-worker.js` pour l'installation et la consultation hors ligne
  (lecture seule, cache réseau-prioritaire des requêtes GET).
- `src/covoit/models.py`: schéma SQLModel (utilisateurs, groupes, adhésions,
  véhicules, modèles récurrents, trajets, tronçons, prix mensuels, bilans,
  validations, remboursements, corrections et écarts reportés).
- `src/covoit/billing.py`: calcul pur (sans DB) du coût d'un tronçon, de la
  répartition entre occupants, des dettes par trajet, des soldes nets et de
  la simplification des virements. Entièrement testé unitairement.
- `src/covoit/recurrence.py`: génération pure des dates d'occurrence d'un
  modèle récurrent (jours de semaine + horizon).
- `src/covoit/services.py`: règles métier reliant les modèles à la logique
  pure (adhésion aux groupes, véhicules partagés, trajets/participation,
  bilan mensuel, corrections post-clôture).
- `src/covoit/routers/`: endpoints FastAPI, un fichier par domaine.
- `src/covoit/security.py`, `deps.py`: authentification locale par jeton de
  session (mots de passe hachés avec bcrypt, jetons hachés en base).

## Périmètre fonctionnel de cette v1

Implémenté et testé:

- Comptes locaux créés par un administrateur unique, mot de passe temporaire
  changé à la première connexion, réinitialisation par l'administrateur.
- Groupes: création libre, invitation par le gestionnaire avec acceptation
  obligatoire, transfert de gestion, changement du conducteur par défaut par
  tout membre actif, départ d'un membre (bloqué pour l'unique gestionnaire),
  archivage.
- Véhicules multi-énergies (essence, diesel, éthanol, électrique) avec
  consommation par énergie, partage avec un ou plusieurs groupes.
- Trajets ponctuels détaillés en tronçons avec occupants explicites par
  tronçon, tronçons de détour imputés au passager concerné, capacité stricte
  du véhicule (conducteur inclus), liste d'attente lorsque le trajet est
  complet, décision du conducteur sur les demandes.
- Modèles récurrents (jours de semaine + heure), génération idempotente des
  occurrences sur un horizon donné, pause/reprise, suppression qui annule les
  occurrences futures sans toucher à l'historique, liste fixe de passagers
  avec acceptation préalable.
- Prix mensuel par véhicule et par source d'énergie, saisi par le
  propriétaire; bilan bloqué tant qu'un prix utilisé manque.
- Calcul du bilan: coût par tronçon réparti également entre occupants
  (conducteur inclus), solde net du groupe avec virements minimaux suggérés,
  validation requise des seuls participants du mois, clôture automatique
  dès que tous ont validé, remboursements déclarés puis confirmés par le
  bénéficiaire, corrections tracées après clôture (portant sur la distance
  d'un tronçon) qui reportent l'écart de solde sur le bilan suivant.
- Export CSV du bilan (soldes et virements suggérés).
- PWA statique (`web/`): connexion, changement de mot de passe, création de
  comptes par l'administrateur, groupes (création/invitation/acceptation/
  gestion), véhicules, création de trajets ponctuels et gestion de leur
  statut/participation, modèles récurrents (création, pause/reprise,
  suppression, génération d'occurrences), bilan mensuel (consultation,
  validation, remboursements, export CSV).

Volontairement hors périmètre de cette v1 (voir `SPEC.md` pour le contexte
complet), à traiter dans une itération suivante:

- Intégration cartographique OpenStreetMap réelle (recherche d'adresse,
  géocodage): les lieux sont de simples champs texte, les distances restent
  saisies manuellement comme spécifié.
- Notifications in-app et rappels configurables.
- Export PDF (seul le CSV est fourni).
- Promotion automatique de la liste d'attente lorsqu'une place se libère
  après annulation d'un participant déjà accepté.
- Génération planifiée (cron) des occurrences récurrentes: le bouton/
  endpoint de génération doit être déclenché explicitement (ou via une tâche
  planifiée à ajouter côté exploitation).
- Corrections post-clôture: seule la distance d'un tronçon est modélisée
  (via l'API; pas encore d'écran dédié dans la PWA), la structure d'audit
  (`LedgerCorrection`) est prête pour être étendue à d'autres champs si besoin.
- Éditeur multi-tronçons/détours dans la PWA: la création de trajet dans
  l'interface ne couvre qu'un tronçon unique (tous les participants cochés
  sont à bord de bout en bout); les tronçons détaillés et les détours restent
  modifiables via l'API (`PUT /trips/{id}/segments`).
- Icône PWA fournie en SVG uniquement (limite connue: rendu d'écran d'accueil
  moins fiable sur iOS/Safari qu'un jeu d'icônes PNG dédié).

## Tests

- `tests/unit/`: logique pure de facturation et de récurrence (aucune
  dépendance HTTP/DB), rapide et déterministe.
- `tests/integration/`: scénarios bout en bout via `TestClient` FastAPI avec
  une base SQLite en mémoire dédiée à chaque test (droits d'accès, capacité
  et liste d'attente, cycle de vie du bilan mensuel, remboursements,
  récurrence, corrections post-clôture, annuaire groupes/utilisateurs/
  véhicules pour la PWA).
- Validation manuelle de bout en bout de la PWA effectuée dans un navigateur
  réel (connexion, création de compte/groupe, invitation, véhicule, trajet,
  bilan, remboursement, modèle récurrent).
