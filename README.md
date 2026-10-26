# ⛽️ Fuel Alert Bot — Luxembourg, Belgique & France

Bot de surveillance des prix des carburants (Diesel, SP95, SP98) et du mazout de chauffage.
Une notification est envoyée via **ntfy.sh** dès que le Luxembourg ou la Belgique changent leurs prix, avec la France en comparaison.

---

## ✨ Fonctionnalités

- **3 pays comparés** : Luxembourg, Belgique et France, avec le pays le moins cher désigné pour chaque carburant 🏆
- **Vérification toutes les 5 minutes**, jour et nuit
- **Dates de validité réelles**, lues sur chaque site officiel
- **Prix affichés comme à la pompe**, à 3 décimales
- **Hausse ou baisse** indiquée pour chaque prix depuis la notification précédente
- **Pays indépendants** : la panne d'un site ne bloque pas les autres
- **Alertes techniques** par mail et sur un canal ntfy séparé, en cas de panne

---

## 🌍 Sources officielles

| Pays | Produits | Source |
|---|---|---|
| 🇱🇺 Luxembourg | Diesel, SP95, SP98 | carbu.com (prix maximum officiels) |
| 🇱🇺 Luxembourg | Mazout | petrol.lu |
| 🇧🇪 Belgique | Diesel, SP95, SP98, mazout | SPF Économie (tarif officiel) |
| 🇫🇷 France | Diesel, SP95-E10, SP98 | prix-carburants.gouv.fr (prix typique des stations, hors autoroute et sur autoroute) |
| 🇫🇷 France | Mazout | Bulletin pétrolier de la Commission européenne (moyenne nationale hebdomadaire) |

La France est affichée à titre de comparaison : elle ne déclenche jamais de notification à elle seule.

---

## 📋 Exemple de notification

```
⛽️🚨 Alerte Carburants
🇧🇪 La Belgique change ses prix !

📅 🇱🇺 Carburants dès le 23/10 · Mazout dès le 23/10
📅 🇧🇪 Carburants dès le 27/10 · Mazout dès le 27/10
📅 🇫🇷 Carburants relevés le 26/10 · Mazout : prix du 19/10, publié le 21/10

🟡 DIESEL | 🏆 Go Lux. !
🇱🇺 2.054€ (⚖️ Stable)
🇧🇪 2.444€ (📈 Hausse de +0.016€)
🇫🇷 2.378€ (📈 Hausse de +0.003€) hors autoroute
🇫🇷 2.462€ (⚖️ Stable) sur autoroute 🛣️

🔥 MAZOUT CHAUFFAGE | 🏆 Go Lux. !
🇱🇺 1.544€ (⚖️ Stable)
🇧🇪 1.586€ (📈 Hausse de +0.042€)
🇫🇷 1.930€ (⚖️ Stable) moyenne nationale
```

---

## ⚙️ Fonctionnement

| Workflow | Rôle |
|---|---|
| **Fuel Price Checker** | Vérifie les prix, envoie la notification si besoin, puis lance lui-même le run suivant au prochain multiple de 5 minutes |
| **Watchdog** | Toutes les 10 minutes, relance la chaîne si elle s'est arrêtée (panne GitHub) |
| **Test des alertes** | À lancer à la main : envoie un mail et une alerte ntfy de test |
| **Test France** | À lancer à la main : affiche les prix français calculés, sans rien envoyer |

| Fichier | Rôle |
|---|---|
| `bot.py` | Le bot |
| `prices_cache.json` | La mémoire du bot : derniers prix connus, état des sources, incidents en cours |
| `history.csv` | Journal de tous les changements de prix détectés, avec leur heure |
| `test_alert.py`, `test_france.py` | Scripts des deux tests manuels |

---

## 🔧 Installation

### 1. Le dépôt
Le dépôt doit être **public** : la vérification toutes les 5 minutes dépasse le quota de minutes gratuites d'un dépôt privé.

### 2. Les secrets
Dans **Settings → Secrets and variables → Actions**, crée :

| Secret | Contenu |
|---|---|
| `NTFY_URL` | Le canal ntfy des notifications de prix, ex. `https://ntfy.sh/mon-canal-prix` |
| `NTFY_ALERT_URL` | Un canal ntfy séparé pour les alertes techniques, ex. `https://ntfy.sh/mon-canal-alertes` |
| `MAIL_ADDRESS` | L'adresse Gmail qui envoie et reçoit les alertes |
| `MAIL_APP_PASSWORD` | Un mot de passe d'application Google (16 caractères, sans espaces) |

Les secrets restent invisibles, même dans un dépôt public.

### 3. Les permissions
Dans **Settings → Actions → General → Workflow permissions**, coche **Read and write permissions**.

### 4. Le démarrage
1. Onglet **Actions** → **Fuel Price Checker** → **Run workflow**
2. La chaîne des 5 minutes démarre et le Watchdog prend le relais en cas de coupure.
3. Lance **Test des alertes** une fois pour vérifier la réception du mail et de l'alerte ntfy.

---

## 📱 Recevoir les notifications

1. Installe l'app **ntfy** (App Store ou Google Play, gratuite)
2. Ouvre ntfy → **+** → entre le nom du canal
3. Les notifications arrivent dès qu'un prix change

---

## 🛑 Mettre le bot en pause

Dans l'onglet **Actions**, désactive **Fuel Price Checker** et **Watchdog** (**⋯** → **Disable workflow**).
Pour le relancer : réactive les deux, puis lance **Fuel Price Checker** à la main.
