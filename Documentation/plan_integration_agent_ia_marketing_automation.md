# Intégration de l'Agent IA Prédictif — Vérification de couverture & plan d'intégration

## 1. Vérification de couverture des points de la présentation

Chaque point évoqué dans le deck (`Presentation_IA_Marketing_Automation`) est confronté au squelette de code livré précédemment (`ai_agent_marketing.zip`).

| Point évoqué (slide) | Statut | Où c'est traité | Commentaire |
|---|---|---|---|
| Scoring prédictif ML (XGBoost/LightGBM) — slide 5, 7 | ✅ Couvert | `models/propensity_model.py` | `PropensityPredictor` + préprocesseur sklearn |
| Next Best Action — slide 5, 7 | ✅ Couvert | `models/recommender.py` | Sélection du produit par client |
| Send Time Optimization — slide 5, 7 | ⚠️ Couvert avec hypothèses | `models/timing.py` | Clustering K-Means sur proxys (dernière connexion, nb transactions) — pas d'historique d'engagement réel, mapping cluster → créneau arbitraire à valider |
| Routing multi-canal intelligent — slide 5, 7 | ⚠️ Couvert partiellement | `models/recommender.py::_resolve_channel` | Seul le fallback Push App → SMS (token invalide) est réellement vérifié ; disponibilité SMS/Email/Agence non contrôlée |
| Filtrage risque & conformité (BAM/CNDP/pression) — slide 5, 11 | ✅ Couvert | `rules/compliance.py` | `BankComplianceEngine`, 3 règles conformes au cahier des charges |
| Explicabilité XAI (SHAP) — slide 11 | ✅ Couvert | `models/propensity_model.py` | Valeurs SHAP calculées par client |
| Architecture non intrusive, hybride batch + API — slide 9 | ✅ Couvert | `pipelines/daily_batch.py`, `api/main.py` | Batch nocturne + micro-service temps réel |
| 100 % on-premise, aucune donnée PII externe — slide 9 | ✅ Couvert par construction | Ensemble du projet | Aucun appel à une API IA tierce |
| Nouveaux champs BDD (`next_best_action`, `propensity_score`, `recommended_channel`, `optimal_time_slot`, `eligibility_status`) — slide 13 | ✅ Couvert | `sql/001_create_ai_customer_recommendations.sql` | Table conforme au schéma du deck |
| Webhook CRM agence — mentionné implicitement (canal agence, slide 7) | ✅ Couvert (partiel) | `api/main.py` | Endpoint + retries `tenacity` ; contrat de payload et authentification à confirmer avec l'équipe CRM |
| Interface marketing en glisser-déposer (segments dynamiques) — slide 13 | ⛔ Hors périmètre du code | — | C'est la brique **Ciblage** de votre solution de Marketing Automation ; le squelette expose seulement les champs qu'elle doit consommer, pas l'UI |
| **Définition des Parcours** — non détaillé dans le deck initial | ❌ Non couvert | — | Absent du cahier des charges d'origine et du squelette. Objet de la section 2.2 |
| **Définition des Campagnes** (objectif, contraintes, délai, canal, sélection cible + parcours, périodes) — non détaillée dans le deck initial | ❌ Non couvert | — | Absent du cahier des charges d'origine et du squelette. Objet de la section 2.3 |
| Frequency capping multi-campagnes simultanées | ⚠️ Partiel | `rules/compliance.py` | La règle des 14 jours est calculée par client mais rien n'orchestre la pression cumulée entre plusieurs campagnes actives en même temps. Objet de la section 2.4 |
| Roadmap 10 semaines, rôles & responsabilités — slides 15, 17 | N/A | — | Éléments de gouvernance de projet, non codables |
| Bénéfices attendus (+25 à 40 % conversion, -30 % coûts, 0 % risque réglementaire) — slide 19 | N/A | — | KPI cibles à mesurer a posteriori via le pilote A/B test |

**Synthèse** : les quatre capacités IA (scoring, NBA, STO, routing) et le socle conformité/architecture sont couverts par le squelette livré. Les deux angles morts — **comment la sortie de l'agent IA s'articule avec votre Ciblage, vos Parcours et vos Campagnes existants** — sont ceux sur lesquels porte votre question, et font l'objet de la section suivante.

---

## 2. Mode et moyens d'intégration avec votre solution de Marketing Automation

Votre solution dispose déjà de trois briques : **Ciblage** (depuis data lake ou par injection), **Parcours**, et **Campagnes** (objectif, contraintes, délai, canal — orchestrant quelles cibles et quels parcours dérouler, sur quelle période). L'agent IA ne remplace aucune de ces briques : il vient **enrichir la donnée que la brique Ciblage consomme**, en amont.

### 2.1 Contrat de données (interface commune)

Tout repose sur la table `ai_customer_recommendations`, rafraîchie chaque nuit, qui devient le point de contact unique entre l'agent IA et votre solution :

```
client_id | next_best_action | propensity_score | recommended_channel |
optimal_time_slot | optimal_day | eligibility_status | exclusion_reason | model_version
```

Recommandation : exposer une **vue gouvernée** `v_ai_recommendations_eligible` qui filtre déjà `eligibility_status = TRUE`. Cela évite qu'un utilisateur métier construise par erreur un segment incluant des clients exclus pour raison de conformité (surendettement, absence de consentement CNDP, pression commerciale) — la vue "cache" structurellement le risque plutôt que de compter sur la discipline de chacun.

### 2.2 Brique Ciblage — deux modes d'alimentation

Votre message précise que la brique Ciblage sait consommer **soit depuis le data lake, soit par injection**. Le squelette doit donc produire les deux formats en sortie du batch nocturne, sans dupliquer la logique métier :

**Mode A — Lecture directe (si votre Ciblage peut interroger une base externe)**
- Connexion (FDW PostgreSQL, JDBC/ODBC, ou simple réplication) vers `v_ai_recommendations_eligible`.
- L'écran de segmentation en glisser-déposer déjà présent dans votre outil (`IA_Propension >= 0.70 ET IA_Canal == 'PUSH_APP'`, visible slide 13) fonctionne alors nativement puisque les champs sont exposés comme des attributs client standards.

**Mode B — Injection (si votre Ciblage ne peut pas interroger de base externe)**
- Le pipeline `daily_batch.py` exporte, après filtrage de conformité, un fichier ou un appel API (`client_id`, `next_best_action`, `propensity_score`, `recommended_channel`, `optimal_time_slot`, `optimal_day`) pour les seuls clients éligibles.
- Cet export est injecté comme un jeu d'attributs custom dans le référentiel Ciblage, via le connecteur d'injection déjà existant (SFTP/CSV ou API REST), à la même cadence nocturne.

Les deux modes partagent la même source (`v_ai_recommendations_eligible`) — un seul job d'export à ajouter au pipeline, pas deux logiques différentes.

### 2.3 Brique Parcours — comment l'IA les sélectionne sans les créer

L'agent IA **ne construit pas** de parcours : il indique lequel activer. Les parcours (contenus, séquences, templates par canal) restent conçus et maintenus par les équipes Marketing Ops dans votre outil.

Le lien se fait par une table de correspondance, simple et pilotable sans redéploiement du pipeline ML :

```
nba_to_parcours_mapping (next_best_action, recommended_channel) -> parcours_id
```

Exemple : `('CREDIT_CONSO', 'PUSH_APP') → parcours_credit_push_v2`, `('CREDIT_CONSO', 'SMS') → parcours_credit_sms_v1`. Marketing Ops peut faire évoluer un parcours ou le remplacer sans toucher au code de l'agent IA.

`optimal_time_slot` et `optimal_day` n'influencent pas la structure du parcours : ils paramètrent le **nœud de déclenchement/attente** du parcours (déclenchement individualisé par client), pas la campagne elle-même. Pour le canal `AGENCY_CALL`, il n'y a pas de "parcours" au sens marketing automation : c'est le webhook temps réel (`api/main.py`) qui pousse l'opportunité directement au CRM agence.

### 2.4 Brique Campagne — le point d'orchestration

C'est la brique qui répond concrètement à votre question "qui cibler, quel parcours dérouler, pendant quelle période". Une campagne se définit avec :

| Champ campagne | Origine / logique |
|---|---|
| **Objectif** | Généralement 1 campagne = 1 `next_best_action` (ex. "Relance Crédit Conso T3" → cible `next_best_action = 'CREDIT_CONSO'`) |
| **Cible (segment)** | Résolue via la brique Ciblage, filtrée sur `v_ai_recommendations_eligible` avec un seuil métier (ex. `propensity_score >= 0.70`) |
| **Parcours** | Résolu automatiquement par client via `nba_to_parcours_mapping`, selon son `recommended_channel` — pas un choix unique et figé pour toute la campagne |
| **Canal** | Par défaut = `recommended_channel` de chaque client (recommandé, pour préserver l'intérêt du routing multi-canal) ; possibilité de forcer un canal unique si la campagne l'exige |
| **Contraintes** | `eligibility_status = TRUE` obligatoire + plafond de volume/jour + vérification de pression **cumulée entre campagnes** (voir ci-dessous) |
| **Délai / période** | Fenêtre `date_debut` → `date_fin` de la campagne ; à l'intérieur de cette fenêtre, `optimal_day`/`optimal_time_slot` déterminent le moment exact d'envoi propre à chaque client |

### 2.5 Point d'attention : la pression commerciale à l'échelle de plusieurs campagnes

`rules/compliance.py` calcule aujourd'hui `days_since_last_solicitation` par client, mais rien ne garantit qu'un client ciblé par la campagne A ne soit pas sollicité le même jour par la campagne B. Il manque une **table centrale de journal des sollicitations**, alimentée par toutes les campagnes (existantes et pilotées par l'IA) :

```
solicitation_ledger (client_id, campaign_id, channel, sent_at)
```

Deux usages :
1. `rules/compliance.py` calcule `days_since_last_solicitation` à partir de ce ledger réel plutôt que d'une donnée simulée.
2. Le moteur de campagne consulte ce même ledger avant activation, pour appliquer un plafond de pression **global**, pas seulement au sein d'une campagne.

C'est également ce ledger qui permettra de constituer proprement le **groupe de contrôle** du pilote A/B test prévu en semaines 9-10 de la roadmap.

---

## 3. Ce qu'il reste à ajouter au squelette pour rendre ce plan opérationnel

| Ajout | Fichier concerné | Effort estimé |
|---|---|---|
| Vue gouvernée `v_ai_recommendations_eligible` | `sql/004_governed_view.sql` (à créer) | Faible |
| Job d'export nightly (Mode A + Mode B) | `pipelines/daily_batch.py` | Moyen |
| Table + logique `nba_to_parcours_mapping` | `sql/` + `models/recommender.py` | Faible |
| Table `solicitation_ledger` + branchement réel dans `compliance.py` | `sql/` + `rules/compliance.py` | Moyen |
| Contrat d'API/format d'injection avec votre outil de Ciblage | `api/main.py` ou nouveau module `integrations/` | À cadrer avec l'équipe Devs Platform |

Ces cinq chantiers correspondent exactement à l'atelier de cadrage technique évoqué en conclusion du deck (slide 19) — ils peuvent servir de base à son ordre du jour.
