# Handoff — Conception de l'orchestrateur JidoTa (daemon Linear → Claude Code)

Date de la session : 2026-10-15
Branche git au moment de la session : `add-plan-agent-tasks-skill` (modifications non commitées sans rapport avec ce handoff : `skills/check`, `skills/plan-tickets`, `skills/task-to-pr`, `skills/test`).

## Objet

Session `/stress-idea` (sans mode `schema` : aucun contrat d'entrée structuré pour une autre skill n'a été produit) sur l'idée de l'utilisateur : un orchestrateur qui poll Linear, n'invoque Claude Code en headless que lorsqu'il y a du travail, et reste seul à écrire dans Linear.
L'interview a été menée en 4 rounds, une question à la fois, sous forme d'arbre de décisions. **La compréhension commune a été confirmée par l'utilisateur.** Rien n'a encore été écrit dans le dépôt (ni ADR, ni ARCHITECTURE.md, ni code).

Références à lire (non dupliquées ici) :
- `README.md` — concept JidoTa (Jidoka/Takt), statuts Linear, principes, safeguards, mesure.
- `scripts/linear-workflow/README.md` — script qui crée les statuts JidoTa dans une équipe Linear.
- `skills/task-to-pr/SKILL.md` — skill exécutée par l'agent ; rapport final à format fixe (`result: done | blocked`, PR, `Blocked by`…).
- `skills/check/SKILL.md`, `skills/plan-tickets/SKILL.md`, `skills/test/SKILL.md`, `skills/review/SKILL.md`.

## Idée initiale de l'utilisateur (résumé)

Script (Node, Python ou .NET) lancé par cron toutes les 5 min, qui meurt à chaque fois :
1. interroge Linear (GraphQL), issues « à traiter » filtrées par label/statut ; rien → fin ;
2. pour chaque issue, construit un prompt (titre, description, critères, numéro) et lance `claude -p "implémente l'issue X..."` avec `--output-format json` / `--output-format --stream-json --verbose`, `--allowedTools`, répertoire de travail ;
3. repasse l'issue en « à revoir » ou « fait », ajoute un commentaire (résumé, lien branche/PR). C'est le script qui écrit dans Linear, pas l'agent.
Verrou : l'issue passe en « en cours » avant le lancement. Auth Claude : `claude setup-token`. Collecte de données sur le process via le stream.

### Hypothèses de départ invalidées pendant la session
1. **Cron + script qui meurt** : incompatible avec un appel synchrone à Claude (runs de 15–60 min avec attente CI) → chevauchement de N instances, plus de « point de contrôle unique ».
2. **Le script pose « fait »** : contraire au principe JidoTa — `Done` est posé par l'humain après revue et merge.
3. **`--output-format --stream-json`** : syntaxe invalide. Forme correcte : `--output-format stream-json --verbose`. `json` et `stream-json` s'excluent ; l'événement final `result` du stream suffit.
4. **« Point de contrôle unique »** : ne couvrait que Linear ; `task-to-pr` écrit dans GitHub (push, PR, CI).

---

## Round 1 — racines de l'arbre

### R1-Q1 — Modèle d'exécution
Contradiction relevée : « webapp qui surveille » vs « orchestrateur en continu » vs « script cron qui meurt ». Un run `task-to-pr` dure 15–60 min ; un cron à 5 min lancerait 3 à 12 instances concurrentes écrivant dans Linear.

| Option | Description | Statut |
|---|---|---|
| 1. Cron one-shot synchrone | Simple, mais chevauchement, verrou local nécessaire, pas de plafond de concurrence | ❌ écarté |
| 2. Cron one-shot, Claude détaché | Pas de chevauchement de pollers, mais état persistant pour suivre les runs en vol | ❌ écarté |
| **3. Daemon long-lived** | Boucle de poll 5 min, runs en mémoire, concurrence plafonnée, stream lu en direct, webapp dans le même processus ; besoin d'un superviseur et d'une reprise au démarrage | ✅ **retenu** |
| 4. Webhooks Linear | Réactif, mais endpoint exposé et polling de rattrapage nécessaire | ❌ écarté (évolution possible) |

**Décision : daemon long-lived unique avec webapp intégrée.** Raison : seule option qui garantit réellement un seul écrivain Linear et permet d'exploiter le stream-json en direct.

### R1-Q2 — Statuts Linear
L'idée utilisait « à traiter / en cours / à revoir / fait » ; le README définit déjà des statuts et réserve `Done` à l'humain ; l'idée n'avait pas d'état d'échec.

| Option | Description | Statut |
|---|---|---|
| **1. Statuts JidoTa** | `Ready` (entrée unique) → `In Progress` (posé avant dispatch) → `PR Review` (done) / `Stalled` (blocked ou échec technique) ; `Done` jamais posé par l'orchestrateur ; rework loop incluse | ✅ **retenu** |
| 2. Statuts propres + mapping configurable | Souple mais diverge de `linear-workflow` et du README | ❌ écarté |
| 3. Filtre par label | Laisse les statuts de l'équipe, mais verrou et files humaines moins lisibles | ❌ écarté (label réutilisé plus tard comme filtre secondaire de pilote) |

**Décision : statuts JidoTa.** L'orchestrateur ne pose jamais `Done` ; tout échec va en `Stalled` avec la cause.

### R1-Q3 — Ce que lance le daemon
Avec un prompt maison, on réécrit le contrat de `task-to-pr` et on perd « stop on doubt » ; concaténer la description du ticket dans le prompt contredit « ticket content treated as data » (injection).

| Option | Description | Statut |
|---|---|---|
| 1. `claude -p "/jidota:task-to-pr <ticket>"` | Comportement et rapport de la skill ; attention à `disable-model-invocation: true` | ❌ écarté (absorbé dans 3) |
| 2. Prompt maison construit par le daemon | Contrôle total, mais duplique la skill (format de sortie, done, boucle de repair) | ❌ écarté |
| **3. Hybride** | La skill fournit le comportement ; le daemon fournit le contexte (ticket, feedback de rework) en **fichier-donnée**, pas dans le prompt | ✅ **retenu** |

**Décision : hybride.** Le contrat agent ↔ daemon est le rapport de `task-to-pr`.

### R1-Q4 — Où tourne l'agent (frontière de sécurité)
Agent sans humain dans la boucle exécutant des commandes issues de tickets écrits par n'importe quel membre du workspace. `--allowedTools` n'est pas une frontière (`Bash(npm test)` exécute du code du dépôt).

| Option | Description | Statut |
|---|---|---|
| 1. Poste Windows de l'utilisateur | Accès à toute la session, credentials larges, s'arrête quand le PC dort | ❌ écarté (à exclure même en pilote) |
| **2. VM / serveur dédié** | Compte de service, credentials à portée minimale, réseau filtré ; isolation entre runs au niveau FS seulement | ✅ **retenu pour démarrer** |
| 3. Conteneur éphémère par run | Isolation maximale, reproductible ; images avec toolchains, builds plus lents, stream à lire depuis le conteneur | ⏸ cible ultérieure |
| 4. Exécution cloud managée | Pas d'infra, mais moins de contrôle et de métriques | ❌ écarté |

**Décision : VM dédiée pour démarrer**, conteneurs par run plus tard.

### R1-Q5 — Authentification Claude
`setup-token` = token OAuth longue durée rattaché à un abonnement Pro/Max personnel. Conséquences : quotas partagés (fenêtres 5 h / hebdo) avec l'usage interactif, `total_cost_usd` indicatif et non facturé, question de conditions d'usage pour un service automatisé.

| Option | Description | Statut |
|---|---|---|
| **1. `setup-token` sur le compte personnel** | Démarrage immédiat ; tous les inconvénients ci-dessus | ✅ **retenu** (contre la recommandation) |
| 2. `setup-token` sur compte dédié (siège Team/Enterprise) | Quotas séparés, coût fixe, débit plafonné | ❌ écarté (était le repli pilote recommandé) |
| 3. Clé API dans un workspace Console dédié | Coût réel par ticket, plafond de dépense = coupe-circuit, limites qui montent | ❌ écarté (c'était la recommandation) |
| 4. Bedrock / Vertex | Seulement si facturation cloud déjà centralisée | ❌ écarté |

**Décision : `setup-token` personnel, conséquences acceptées** : quotas partagés, métrique de coût = tokens / part de quota (pas d'euros), conditions d'usage à faire vérifier par l'utilisateur. Tension notée avec le principe « credentials à portée minimale » de R1-Q4 → traitée en R2-Q7 / R2-Q8.

### R1-Q6 — Un dépôt ou plusieurs
Un ticket Linear standard ne dit pas dans quel dépôt travailler.

| Option | Description | Statut |
|---|---|---|
| 1. Un seul dépôt pour le pilote | Le plus simple | ❌ écarté (c'était la recommandation, avec config au format de l'option 2) |
| **2. Plusieurs dépôts, mapping projet Linear → dépôt dans la config du daemon** | Explicite, centralisé, à maintenir | ✅ **retenu** |
| 3. Mapping par label `repo:x` | Label oublié/erroné → mauvais dépôt | ❌ écarté |
| 4. Dépôt indiqué dans le ticket | Vecteur d'injection (n'importe quel auteur désigne un dépôt) | ❌ écarté |

**Décision : plusieurs dépôts dès le départ, mapping projet Linear → dépôt dans la config du daemon.** Le daemon, pas le ticket, décide où l'agent écrit.

---

## Round 2 — branches dérivées

### R2-Q1 — État persistant, verrou, reprise après crash
Trous relevés : pas de compare-and-swap dans Linear (il faut garantir une instance unique), tickets orphelins en `In Progress` après crash, processus `claude` fantôme qui survit au daemon.

| Option | Description | Statut |
|---|---|---|
| 1. Aucun état local, Linear seule vérité | Perte du lien avec le run (logs, PID, worktree), impossible de distinguer ses `In Progress` | ❌ écarté |
| **2. SQLite local** | Table des runs (ticket, PID, worktree, début, statut), verrou d'instance unique, réconciliation au démarrage, kill des orphelins | ✅ **retenu** |
| 3. Reprise réelle des runs interrompus | Masque les pannes, risque de double travail/push | ❌ écarté |

**Décision : SQLite + verrou d'instance unique + réconciliation au démarrage** (run mort → `Stalled` « interrompu » avec logs partiels, orphelins tués). **Aucune reprise automatique.** Les tickets pris sont marqués par un **utilisateur bot Linear** (précisé en R3-Q5 : délégation à une app OAuth).

### R2-Q2 — Plafond et politique de concurrence
Ressources partagées : quota de l'abonnement, CPU/RAM de la VM (builds, navigateur), même dépôt (conflits de fichiers).

| Option | Description | Statut |
|---|---|---|
| 1. Un seul run à la fois | Sûr, débit faible (~30 tickets/jour max) | ❌ écarté |
| 2. Plafond global N sans contrainte par dépôt | Conflits possibles dans un même dépôt | ❌ écarté |
| **3. Plafond global N + 1 run max par dépôt** | Sérialise par dépôt, parallélise entre dépôts | ✅ **retenu, N = 2** |
| 4. Parallèle dans un dépôt si `touches` disjoints | Dépend de la qualité des `touches` | ⏸ évolution possible |

### R2-Q3 — Ordre de prise et dépendances
Sans logique de dépendance, `task-to-pr` refuse un ticket dont un prérequis n'est pas approuvé/mergé → `Stalled` inutile, quota gaspillé, bruit dans l'inbox humaine.

| Option | Description | Statut |
|---|---|---|
| 1. Aucune logique, discipline humaine | Un oubli coûte un run | ❌ écarté |
| **2. Relations Linear `blocked by`** | Ticket non éligible reste en `Ready` (ignoré ce cycle, jamais un échec), repris quand le bloqueur est `Done` ; pas d'empilement | ✅ **retenu** |
| 3. Idem + empilement si PR bloqueuse approuvée | Meilleur débit, mais lecture GitHub et rebase en cascade | ⏸ évolution possible |
| 4. Parser `depends_on` du YAML du ticket | Texte libre modifiable, doublon avec Linear | ❌ écarté |

**Décision : `blocked by` + tri par priorité Linear, puis rang manuel / date de création.** Conséquence : `/jidota:check` devra vérifier que `depends_on` et les relations Linear concordent.

### R2-Q4 — Qui écrit dans GitHub
`task-to-pr` pousse, ouvre la PR, attend et répare la CI avec `gh` → l'agent a un credential GitHub en écriture ; « jamais push sur main / jamais merge » n'existait que dans le prompt.

| Option | Description | Statut |
|---|---|---|
| 1. Agent avec token ordinaire (celui de l'utilisateur) | Peut souvent merger, pousser sur main, toucher d'autres dépôts | ❌ écarté |
| **2. Agent avec identité bot à portée minimale** | Compte machine, PAT fine-grained limité aux dépôts mappés (`contents` + `pull_requests` write), rulesets serveur ; le daemon vérifie la PR via l'API avant d'écrire dans Linear | ✅ **retenu** |
| 3. Le daemon pousse et ouvre la PR | Isolation max, mais casse la boucle CI de `task-to-pr` | ❌ écarté |

Note : GitHub App écartée au profit d'un compte machine + PAT fine-grained, car les tokens d'installation expirent en 1 h et un run avec CI peut durer plus.
**Décision : compte machine + PAT fine-grained + rulesets** (pas de push direct sur la branche par défaut, le bot ne peut ni approuver ni merger). Principe reformulé : l'agent écrit dans sa branche et sa PR, le daemon est seul écrivain Linear, GitHub fait respecter les limites.

### R2-Q5 — Invocation headless et contrat de sortie
Le stream-json fournit `system/init`, messages `assistant`/`user` (tool_use, résultats), et un événement final `result` (`subtype`, `is_error`, texte, `num_turns`, `duration_ms`, `usage`, `total_cost_usd`, `session_id`, `permission_denials`). Cas à traiter : pas d'événement `result`, `is_error`, rapport absent, rapport `done` sans PR réelle.

| Option | Description | Statut |
|---|---|---|
| 1. Parser le texte du rapport | Rien de plus à faire, mais fragile si la skill change | ⏸ **repli** |
| **2. `--json-schema`** | Sortie finale validée contre un schéma versionné côté daemon (`result`, `pr_url`, `branch`, `blocked_by`, `changed_files`…) | ✅ **retenu** |
| 3. Fichier `report.json` écrit par l'agent | Pas de garantie de conformité, seconde source de vérité | ❌ écarté |

**Décision : `--output-format stream-json --verbose` + `--json-schema`, repli sur parsing strict.** JSONL brut persisté par run. Toute sortie invalide ou non confirmée par GitHub → `Stalled` avec cause typée (`no_result`, `invalid_report`, `pr_mismatch`) et lien vers le log. Le daemon ne devine jamais.

### R2-Q6 — Permissions de l'agent
En `-p`, un outil non autorisé est refusé (pas de prompt). Plusieurs dépôts = plusieurs toolchains. Une allowlist n'est pas une frontière de sécurité (règles Bash contournables) ; la vraie frontière = VM + tokens + rulesets.

| Option | Description | Statut |
|---|---|---|
| 1. Tout autoriser (`bypassPermissions`) | Perd le signal « action inattendue » | ❌ écarté |
| 2. Allowlist globale | Trop large ou cassante | ❌ écarté |
| **3. Allowlist de base + ajouts par dépôt dans la config du daemon** | `--settings` généré par run ; base = lecture, édition, `git`, `gh pr`, `gh run` ; chaque dépôt déclare build/test | ✅ **retenu** |
| 4. `.claude/settings.json` du dépôt | Dispersé, modifiable par l'agent dans sa branche | ❌ écarté |

**Décision : option 3, WebFetch/WebSearch interdits par défaut** (exfiltration, injection indirecte), autorisables par dépôt. `permission_denials` = métrique + cause `Stalled` `permission_denied` (problème de config, pas de spec).

### R2-Q7 — Budgets par run et coupe-circuit global
Risques : run sans fin (`gh pr checks --watch` sur CI bloquée, test qui ne termine pas) qui occupe un créneau ; cascade globale (quota épuisé, token expiré, disque plein, GitHub en panne) qui viderait toute la file `Ready` en `Stalled`.

| Option | Description | Statut |
|---|---|---|
| 1. Aucune limite supplémentaire | Ni créneaux bloqués ni cascade traités | ❌ écarté |
| 2. Plafonds par run seulement | Cascade non traitée | ❌ écarté |
| **3. Plafonds par run + coupe-circuit global** | Classement des échecs infra vs ticket ; suspension du dispatch | ✅ **retenu** |

**Décision et valeurs :**
- Timeout d'horloge **90 min** (ajustable par dépôt) : kill de l'arbre de processus, `Stalled` cause `timeout`, worktree conservé pour inspection ; `--max-turns` généreux en filet.
- Échecs **infra** : `no_result`, auth, quota/limite de débit, disque, GitHub/Linear indisponible. Échecs **ticket** : `blocked`, `invalid_report`, `permission_denied`.
- Erreur quota/auth ou **K = 2** échecs infra consécutifs → dispatch suspendu ; les tickets restants **restent en `Ready`** ; seul le ticket en cours va en `Stalled` ; pause visible dans la webapp + alerte ; reprise auto après la fenêtre de quota, manuelle sinon.

### R2-Q8 — Token Claude et secrets
Trois secrets sur la VM : token `setup-token`, PAT GitHub, clé Linear. Les sous-processus de l'agent héritent de l'environnement (`CLAUDE_CODE_OAUTH_TOKEN`) → un `env` ou un test piégé lit le token.

| Option | Description | Statut |
|---|---|---|
| 1. Variables d'environnement en clair, tout passé à tous les runs | Une injection lit tout, y compris la clé Linear | ❌ écarté |
| **2. Coffre OS + injection au plus juste** | `claude` ne reçoit que le token Claude et le PAT GitHub ; clé Linear jamais transmise ; utilisateur OS dédié sans accès SQLite/config ; réseau sortant filtré | ✅ **retenu** |
| 3. Idem + passerelle d'auth (`ANTHROPIC_BASE_URL`) | Agent ne voit jamais le token, mais conçu pour clés API, compatibilité incertaine avec un token d'abonnement | ❌ écarté |

**Décision : option 2.** Rotation : date de création du token en config, alerte préventive avant échéance, coupe-circuit en cas d'échec d'auth.

### R2-Q9 — Rework loop
Le daemon doit reconnaître un rework, trouver le feedback (relu dans GitHub, ticket remis en `Ready` dans Linear) et ne prendre que le nouveau.

| Option | Description | Statut |
|---|---|---|
| 1. Feedback dans Linear seulement | Recopie GitHub → Linear, perte du contexte fichier/ligne | ❌ écarté |
| 2. Feedback dans GitHub seulement | Feedback de spec mal placé dans une PR | ❌ écarté |
| **3. GitHub principal + Linear en complément** | Agrégés dans le fichier-donnée ; rework identifié via SQLite + lien PR | ✅ **retenu** |

**Décision : option 3 + règles :** feedback GitHub = dernière review `CHANGES_REQUESTED`, threads non résolus, commentaires postérieurs au commit du dernier run. PR fermée sans merge → repartir de zéro (nouvelle branche, nouvelle PR). Ticket re-`Ready` sans feedback nouveau → `Stalled` « rework sans feedback » sans lancer de run. **Plafond de 3 reworks** → `Stalled` « spécification à revoir ».

### R2-Q10 — OS de la VM, superviseur, toolchains, réseau
| Option | Description | Statut |
|---|---|---|
| 1. VM Linux (Ubuntu LTS) + systemd + proxy | Environnement le plus courant, simple à filtrer/reconstruire | ❌ écarté (recommandation initiale) |
| **2. VM Windows Server + service Windows** | Obligatoire si un dépôt ne se construit/teste que sous Windows | ✅ **retenu** |
| 3. Linux + image Docker de toolchain par dépôt | Complexité des conteneurs dès le pilote | ❌ écarté |

**Décision : Windows Server** (« les apps sont sous Windows »), avec provisionnement scripté, Claude Code en version figée (mises à jour volontaires, télémétrie/auto-update coupés), proxy sortant avec allowlist. Remis en question en R3-Q2 et **confirmé**.
Conséquences Windows relevées : service en session 0 (pas de bureau), lancement de `claude` sous un autre utilisateur, kill de l'arbre via Job Objects, filtrage par domaine impossible avec le pare-feu Windows (proxy séparé), Git Bash requis par l'outil Bash de Claude Code.

### R2-Q11 — Rôle de la webapp
Risques : seconde console de pilotage des tickets (Linear n'est plus la référence) ; surface d'attaque sur une machine portant un token personnel.

| Option | Description | Statut |
|---|---|---|
| 1. Lecture seule stricte | Reprise manuelle en CLI via RDP | ❌ écarté |
| **2. Lecture + actions sur le daemon uniquement** | Pause/reprise du dispatch, annulation d'un run (`Stalled` cause `cancelled`), jamais d'action sur les tickets, actions journalisées avec l'auteur | ✅ **retenu** |
| 3. Poste de commande complet | Doublon avec Linear, casse le point de contrôle unique | ❌ écarté |

Accès : (a) `localhost` + RDP/tunnel ❌ écarté ; **(b) réseau interne + Entra ID + liste d'utilisateurs autorisés** ✅ **retenu**.

### R2-Q12 — Métriques
Données : stream Claude (init, tool_use, usage par message, sous-agents, `result`), daemon (attente en `Ready`, durée, issue, cause typée, rework, pauses), GitHub (taille PR, rondes CI, délai jusqu'au merge). Le JSONL brut contient code, tickets et potentiellement des secrets.

| Option | Description | Statut |
|---|---|---|
| 1. Minimal (`result` + statut) | On ne sait pas où passent temps et quota | ❌ écarté |
| **2. Agrégats + événements dans SQLite** | Tables `runs` (durées, tokens par type, tours, issue, cause, rework) et `tool_events` (outil, durée, erreur, sous-agent) | ✅ **retenu** |
| 3. Idem + OpenTelemetry natif de Claude Code | Domaine et infra en plus | ⏸ évolution possible |

**Décision : option 2.** JSONL brut **masqué** (valeurs des secrets connus remplacées avant écriture), **rétention 90 jours** ; agrégats sans limite ; 3–4 indicateurs dans le commentaire Linear de fin de run.

### R2-Q13 — Langage et stack du daemon
Besoins : service Windows, lancement sous un autre utilisateur, kill d'arbre (Job Objects), webapp Entra ID, JSONL en flux, SQLite, Linear GraphQL, GitHub REST.

| Option | Description | Statut |
|---|---|---|
| **1. .NET (Worker Service + ASP.NET Core)** | `UseWindowsService()`, Microsoft.Identity.Web, Microsoft.Data.Sqlite, P/Invoke (Job Objects, CreateProcessAsUser/WithLogonW), Octokit.NET ; pas de SDK Linear officiel → client GraphQL (HttpClient / StrawberryShake) | ✅ **retenu** |
| 2. Node/TypeScript | SDK Linear officiel, mais service Windows et Job Objects via modules tiers | ❌ écarté |
| 3. Python | Mêmes faiblesses Windows, plus marquées | ❌ écarté |
| Transverse : Claude Agent SDK au lieu de la CLI | Écarté ici sur un argument erroné (« perte de l'isolation par processus séparé ») — corrigé et réexaminé en Q-SDK plus bas | ❌ écarté (confirmé en Q-SDK) |

**Décision : .NET, qui lance la CLI `claude`.**

---

## Round 3 — branches ouvertes par le round 2

### R3-Q1 — Tests UI d'apps Windows depuis un service
Service Windows = session 0 sans bureau → automatisation UI desktop (FlaUI, WinAppDriver) impossible ; avec N = 2, deux runs se disputeraient un même bureau ; un critère purement visuel ferait toujours `blocked`.

| Option | Description | Statut |
|---|---|---|
| **1. Pas de tests UI desktop dans la factory** | Preuve par tests unitaires/intégration (ViewModels, services) ; `plan-tickets`/`check` refusent les critères prouvables seulement à l'écran | ✅ **retenu pour le pilote** |
| 2. Session interactive permanente (autologon) | Mot de passe stocké, verrouillage de session, N = 1 pour les dépôts UI | ❌ écarté |
| 3. Tests UI délégués à la CI (runner self-hosted interactif) | Boucle CI déjà dans `task-to-pr` | ⏸ cible ultérieure recommandée |
| 4. Bureau isolé par run (VM/conteneur Windows) | Chantier le plus lourd | ❌ écarté (prématuré) |

Précision utilisateur : **le pilote porte sur Angular + Web API** (Playwright headless n'est pas concerné par la session 0).

### R3-Q2 — Faut-il vraiment Windows pour Angular + Web API ?
Remise en cause de R2-Q10 : Angular et ASP.NET Core se construisent et se testent sous Linux ; le choix Windows a entraîné toute une cascade de complexité.

| Option | Description | Statut |
|---|---|---|
| **1. Garder Windows Server** | Justifié par des composants Windows-only | ✅ **retenu** |
| 2. VM Linux pour le pilote, Windows plus tard | Supprime la moitié des difficultés du pilote | ❌ écarté (recommandation) |
| 3. Daemon Linux + exécuteur Windows distant | Prématuré | ❌ écarté |

**Décision : Windows confirmé**, car certains composants sont Windows-only (ex. **serveurs OPC**, OPC DA = COM/DCOM). Cascade Windows acceptée en connaissance de cause.

### R3-Q3 — Ce que l'agent peut toucher côté OPC
Risque de sûreté de fonctionnement (agent autonome pouvant écrire des tags OPC sur de vrais équipements via un ticket piégé), état partagé entre runs, DCOM/licences.
Options présentées : 1. simulateur local + aucune route vers l'OT ; 2. abstraction client OPC + doublures ; 3. serveur OPC de dev en lecture seule ; 4. équipements réels (à exclure).
**Décision : OPC hors périmètre de la version de base** (viendra quand l'orchestrateur aura ses fonctionnalités de base). Principe retenu pour plus tard : **option 1 — simulateur local, aucune route réseau de la VM vers l'OT/production, garanti par le réseau et non par le prompt** (VM à positionner comme zone/conduit IEC 62443).

### R3-Q4 — Hébergement de la VM et filtrage sortant
Le filtrage doit être hors de la VM (pare-feu Windows sans filtrage par domaine, contournable depuis la VM).

| Option | Description | Statut |
|---|---|---|
| **1. VM Azure, sous-réseau dédié, NSG + Azure Firewall (règles FQDN), webapp privée** | Filtrage réellement externe ; coût fixe d'Azure Firewall accepté | ✅ **retenu** |
| 2. VM sur site, VLAN dédié, proxy d'entreprise | Dépend de l'équipe réseau | ❌ écarté |
| 3. Proxy sur la VM | Contournable, dette | ❌ écarté |

Flux à autoriser : agent → API Anthropic, GitHub, npm/NuGet (ou miroir) ; daemon → idem + API Linear, Entra ID, Azure Monitor ; entrant → webapp depuis le réseau interne. Sous-réseau à isoler de l'OT le jour d'OPC.

### R3-Q5 — Identité Linear du daemon
| Option | Description | Statut |
|---|---|---|
| 1. Clé API personnelle de l'utilisateur | Détruit la traçabilité (tout en son nom), droits complets | ❌ écarté |
| 2. Compte utilisateur Linear dédié | Siège payant, droits de membre sur tout le workspace | ⏸ **repli** si délégation/scopes indisponibles |
| **3. App OAuth Linear `actor=app` avec délégation** | Sans siège, scopes limités, installée sur les équipes concernées ; le ticket est délégué à l'app, l'assigné humain reste | ✅ **retenu** |

**Décision : option 3.** Le marqueur « pris par le daemon » = la délégation à l'app ; l'assigné humain n'est jamais modifié. Flux OAuth : installation unique + refresh token (stocké dans le coffre).

### R3-Q6 — Canal d'alerte
Angle mort : un daemon mort ne peut pas signaler sa propre mort ; les tickets restent en `Ready` sans bruit.

| Option | Description | Statut |
|---|---|---|
| 1. Teams depuis le daemon | Ne détecte pas la mort du daemon | ❌ écarté |
| 2. E-mail via Graph | Même angle mort | ❌ écarté |
| 3. Ticket Linear « ops » | Mélange exploitation et file de travail | ❌ écarté |
| **4. Azure Monitor (heartbeat + événements → Log Analytics, règles, groupe d'actions)** | Détecte l'absence du daemon | ✅ **retenu, routage vers Teams** |

Événements alertés : dispatch suspendu, token proche de l'échéance, heartbeat absent (~15 min), seuil disque, **ticket `Ready` dans un projet non mappé** (ajout validé à la confirmation finale).

### R3-Q7 — Ce que le daemon écrit dans Linear
Contenu : statut (`PR Review`/`Stalled`), commentaire structuré (issue, résumé, lien PR, cause typée et `Blocked by` pour `Stalled`, indicateurs), PR en pièce jointe. Rapport publié **comme donnée** (bloc cité, sans mentions `@`, sans liens autres que la PR vérifiée).
Second écrivain caché : l'intégration GitHub native de Linear peut déplacer les statuts (PR ouverte → In Review, mergée → Done).

| Option | Description | Statut |
|---|---|---|
| **1. Linear seulement, liaison GitHub conservée, automatismes de statut désactivés ; story = ticket parent Linear, informée par la hiérarchie** | Un seul écrivain | ✅ **retenu** |
| 2. Idem + commentaire sur le ticket parent | Bruit | ❌ écarté |
| 3. Idem + mise à jour story dans Azure DevOps | Intégration en plus, non justifiée | ❌ écarté |
| 4. Garder l'automatisme « merge → Done » | Second écrivain à encadrer | ❌ écarté |

Conséquence : la liaison automatique exige que **le nom de branche contienne l'identifiant Linear** → le daemon impose le nom de branche (R3-Q8).

### R3-Q8 — Clones, worktrees, fichier de contexte
Problèmes : le daemon doit créer le worktree avant `claude` alors que `task-to-pr` en crée un ; le fichier de contexte peut être commité par un `git add -A` ; disque (node_modules, builds) ; état résiduel entre tickets.

| Option | Description | Statut |
|---|---|---|
| 1. Clone neuf par run, supprimé à la fin | Lent, plus d'inspection des échecs | ❌ écarté |
| **2. Miroir par dépôt + worktree par ticket géré par le daemon** | Branche `<ID-Linear>-<slug>` imposée (ou branche existante en rework), contexte **hors du worktree** (`--add-dir`), `task-to-pr` réutilise le worktree | ✅ **retenu** |
| 3. Checkout unique par dépôt avec changement de branche | Contamination entre runs | ❌ écarté |

**Décision : option 2.** Worktree conservé en `PR Review`/`Stalled`, nettoyé au passage en `Done`/`Canceled`/`Duplicate`, à la fermeture de la PR, ou après **14 jours** ; alerte seuil disque via Azure Monitor.

---

## Round 4 — exploitation et mise en service

### R4-Q1 — Mettre à jour le daemon sans `Stalled` parasites
Arrêter le service tue les runs → réconciliation → `Stalled` « interrompu » à chaque déploiement ou patch Windows.

| Option | Description | Statut |
|---|---|---|
| 1. Accepter les interruptions | Bruit à chaque déploiement | ❌ écarté |
| **2. Drain avant arrêt** | Commande/bouton webapp : suspend le dispatch, attend la fin des runs (jusqu'au timeout), puis arrêt ; déploiement = drain → arrêt → MAJ → démarrage ; MAJ Windows dans une fenêtre de maintenance (Azure Update Manager) précédée d'un drain | ✅ **retenu** |
| 3. Run interrompu par crash → retour en `Ready` avec compteur | Reprise automatique, contredit R2-Q1 | ❌ écarté |

Les arrêts imprévus restent des `Stalled` visibles (voulu).

### R4-Q2 — Mise en service
Les chemins critiques sont des chemins d'échec ; le vrai Claude consomme le quota personnel et n'est pas reproductible.

| Option | Description | Statut |
|---|---|---|
| 1. Directement en production | Chemins d'échec testés au hasard | ❌ écarté |
| 2. Mode shadow sur la vraie équipe | Ne valide que lecture/filtre/ordre | ❌ écarté |
| **3. Trois paliers** | (a) **faux agent** rejouant des JSONL enregistrés (done, blocked, invalide, sans `result`, quota, run sans fin) contre une **équipe Linear de test** + **dépôt GitHub bac à sable** Angular/Web API ; (b) vrai `claude` sur le bac à sable ; (c) un vrai dépôt filtré par le label **`jidota-pilot`** | ✅ **retenu** |

Le faux agent devient le **harnais de tests d'intégration** du daemon, rejoué à chaque montée de version de Claude Code et à chaque évolution du schéma de rapport.

---

## Question complémentaire (2026-10-16)

### Q-SDK — Agent SDK ou `claude -p` ?
Question de l'utilisateur après la clôture : « au lieu d'utiliser `claude -p`, on pourrait pas utiliser un agent SDK ? ». Rouvre R1-Q3 et R2-Q13.

**Correction d'une erreur de la session :** en R2-Q13, le SDK avait été écarté pour « perte de l'isolation par processus séparé ». C'est faux : le SDK lance lui-même la CLI `claude` en sous-processus et lui parle par stdio (https://code.claude.com/docs/en/agent-sdk/hosting.md). Le SDK enveloppe la CLI, il ne la remplace pas.

Faits vérifiés dans la documentation Claude Code :

| Point | Agent SDK | CLI `claude -p` |
|---|---|---|
| Langages | TypeScript et Python seulement, **pas de .NET** | Utilisable depuis tout langage (voie documentée hors TS/Python) |
| Processus | Lance la CLI en sous-processus | Processus lancé directement par le daemon |
| Autre utilisateur OS | Python `user` : POSIX uniquement ; TS `spawnClaudeCodeProcess` (spawn personnalisé, types non documentés) | Le daemon .NET contrôle le lancement (`CreateProcessAsUser`, Job Object) |
| Plugin et skill | Option `plugins` (type `local`), prompt `/jidota:task-to-pr` | `--plugin-dir`, prompt `/jidota:task-to-pr` |
| Sortie structurée | `outputFormat: { type: 'json_schema', schema }` → `structured_output` | `--json-schema` → `structured_output`, documenté avec `--output-format json` (non précisé pour `stream-json`) |
| Permissions | `allowedTools`, `permissionMode`, callback `canUseTool`, hooks en fonctions | `--allowedTools`, `--permission-mode dontAsk`, hooks via `--settings` (commandes externes) |
| Budgets | `maxTurns`, `maxBudgetUsd`, abort | `--max-turns`, `--max-budget-usd`, SIGTERM (tue l'arbre des commandes Bash, code 143) |
| Stream | Messages typés | Mêmes données en JSONL |
| Auth | Doc : « Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods » (https://code.claude.com/docs/en/agent-sdk/overview.md) | `CLAUDE_CODE_OAUTH_TOKEN` documenté (plans Pro, Max, Team, Enterprise) |

| Option | Description | Statut |
|---|---|---|
| **1. Garder `claude -p` lancé par le daemon .NET** | Toutes les options nécessaires existent en CLI ; le daemon garde la main sur le processus (utilisateur dédié, Job Object, timeout) | ✅ **retenu** |
| 2. Réécrire le daemon en TypeScript avec le SDK | Messages typés et `canUseTool`, mais perte des atouts .NET de R2-Q13 ; utilisateur Windows dédié à construire via `spawnClaudeCodeProcess` | ❌ écarté |
| 3. Daemon .NET + runner TS/Python par run basé sur le SDK | Callbacks en code, mais un langage, un processus et un contrat de plus | ❌ écarté |

**Décision : garder `claude -p`.** Le SDK n'apporte ni isolation, ni fonctionnalité indispensable, ni support .NET, et la documentation l'oriente vers une clé API. ⏸ À reconsidérer en cas de passage à une clé API, à Linux ou aux conteneurs par run, avec un besoin de règles de permission en code (`canUseTool`).

## Points déduits, confirmés par l'utilisateur à la clôture
- Ticket `Ready` d'un projet non mappé : **alerte** (Azure Monitor → Teams), pas d'ignorance silencieuse.
- Ordre du verrou : délégation + `In Progress` écrits **avant** la création du worktree et le lancement de `claude` ; si l'écriture Linear échoue, aucun run.
- Le masquage des secrets s'applique aussi au commentaire Linear.
- Seul le daemon décide du dépôt ; aucune information du ticket ne peut le désigner.

## À vérifier (faits, pas décisions)
État mis à jour le 2026-10-16 après lecture de la documentation Claude Code.

1. **`disable-model-invocation: true` en `claude -p`** — doc : le flag empêche seulement Claude de charger la skill tout seul, `/name` reste invocable (https://code.claude.com/docs/en/skills.md) et `-p` développe `/skill-name` dans le prompt (https://code.claude.com/docs/en/headless.md). Probablement OK : **confirmer par un vrai run**.
2. **`--json-schema`** — existe, résultat dans `structured_output`, documenté avec `--output-format json` (https://code.claude.com/docs/en/cli-reference.md). **Reste à vérifier : `structured_output` est-il présent dans l'événement `result` en `--output-format stream-json` ?** Sinon : arbitrer entre stream (métriques) et sortie structurée, ou utiliser le repli du parsing texte (R2-Q5).
3. **Exclusion des credentials des sous-processus** — `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` retire les credentials des commandes Bash, hooks et serveurs MCP stdio (https://code.claude.com/docs/en/env-vars.md). Comportement sous Windows non documenté : **à tester**.
4. Délégation d'issues et scopes des apps OAuth Linear disponibles sur le plan Linear de l'utilisateur.
5. Conditions d'usage de l'abonnement Claude personnel pour un usage automatisé (à vérifier par l'utilisateur). La documentation renvoie l'Agent SDK vers les clés API (citation en Q-SDK) ; elle ne dit pas clairement si un daemon interne pour son propre usage est concerné.
6. **Nouveau — attente de CI longue en `-p`** : le travail en arrière-plan est plafonné à 10 min par défaut en `-p` (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`, https://code.claude.com/docs/en/env-vars.md) ; les commandes Bash ont aussi un timeout propre (valeur non vérifiée dans la doc). Un `gh pr checks --watch` (`task-to-pr`) sur une CI plus longue pourrait être coupé : **tester avec la CI réelle des dépôts mappés**.

## Changements induits sur le dépôt JidoTa (non faits)
1. `skills/task-to-pr/SKILL.md` : accepter un worktree et un nom de branche imposés par l'orchestrateur (aujourd'hui : crée/réutilise son worktree, branche `task/<id>-<slug>`).
2. `skills/check/SKILL.md` : vérifier la concordance `depends_on` ↔ relations Linear `blocked by` ; refuser les critères prouvables seulement à l'écran.
3. `README.md` : aligner sur délégation (au lieu d'assignation), coupe-circuit, drain, alertes.

## Prochaines étapes proposées (aucune lancée)
1. `to-adr` : consigner les décisions structurantes dans `docs/decisions/` (daemon unique, VM Windows Azure, `setup-token` personnel, délégation Linear, contrat `--json-schema`, coupe-circuit, compte machine GitHub + rulesets, worktrees gérés par le daemon). Ce handoff peut servir de source directe (options écartées et raisons incluses).
2. `technical-design` : produire l'`ARCHITECTURE.md` du daemon à partir de ces décisions.
3. Lever les vérifications 1, 2, 3, 4 et 6 avant d'écrire du code (1 et 2 conditionnent le contrat agent ↔ daemon, 6 la boucle CI de `task-to-pr`).
4. Appliquer les changements induits sur les skills et le README.

Une mémoire de projet résumant ces décisions existe aussi dans la mémoire Claude de ce dépôt (`orchestrator-design-decisions`).
