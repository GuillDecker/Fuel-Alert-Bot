# ⛽️ Fuel Alert Bot — Luxembourg & Belgique

Bot de surveillance des prix carburants (Diesel, SP95, SP98)  
Notification instantanée via **ntfy.sh** dès qu'un prix change.

---

## 🔧 Installation

### 1. Créer le repo GitHub privé
1. Va sur [github.com/new](https://github.com/new)
2. Nom : `fuel-alert-bot`
3. **Private** ✅
4. Crée le repo

### 2. Uploader les fichiers
Crée les 4 fichiers suivants dans ton repo :
- `bot.py`
- `requirements.txt`
- `.github/workflows/check.yml`
- `prices_cache.json` (contenu : `{"lu": {}, "be": {}}`)

### 3. Créer le Secret NTFY_URL
1. Dans ton repo GitHub → **Settings** → **Secrets and variables** → **Actions**
2. Clique **New repository secret**
3. Nom : `NTFY_URL`
4. Valeur : ton URL ntfy complète, ex: `https://ntfy.sh/fuel-alert-xyz123`
5. **Add secret**

### 4. Activer GitHub Actions
1. Onglet **Actions** de ton repo
2. Si demandé, clique **"I understand my workflows, enable them"**

### 5. Test manuel
1. Onglet **Actions** → workflow **"Fuel Price Checker"**
2. Clique **"Run workflow"** → **"Run workflow"**
3. Vérifie les logs → tu dois voir les prix détectés

---

## 📱 Recevoir les notifications

### Sur iPhone
1. Installe l'app **ntfy** (App Store, gratuite)
2. Ouvre ntfy → **+** → entre ton topic
3. Tu recevras toutes les alertes !

---

## 📋 Format de notification (Exemple)

```
⛽️ Alerte Carburants (14/05)
🇱🇺 Le Luxembourg change ses prix !

🟡 DIESEL | 🏆 Go Lux. !
🇱🇺 1,60€ (📉 Baisse de 0,06€)
🇧🇪 1,75€ (⚖️ Stable)
🟢 SP95 | 🏆 Go Lux. !
🇱🇺 1,55€ (📉 Baisse de 0,06€)
🇧🇪 1,68€ (⚖️ Stable)
🔵 SP98 | 🏆 Go Belgique !
🇱🇺 1,80€ (📈 Hausse de 0,02€)
🇧🇪 1,65€ (📉 Baisse de 0,06€)
```
