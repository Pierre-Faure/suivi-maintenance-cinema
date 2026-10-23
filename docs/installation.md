# Installer l'outil sur un poste

Guide pour la personne qui installe (administrateur ou développeur). Compter
30 minutes, Internet compris. Aucun droit administrateur n'est nécessaire.

## Avant de commencer

- **Ouvrir la session Windows de l'utilisateur**, pas la sienne : Git, uv,
  l'outil et ses données s'installent dans le profil de la session ouverte, et
  l'outil voit les lecteurs réseau de cette session.
- Vérifier dans l'Explorateur que le partage des documents est visible (par
  exemple `Z:\Bâtiment`) et noter son chemin exact.
- Le poste doit accéder à Internet (GitHub, PyPI) pour l'installation et les
  mises à jour.
- Côté dépôt : la branche `prod` doit contenir la version à installer
  (`git push origin main:prod` depuis le poste de développement).

Toutes les commandes se tapent dans **PowerShell** (menu Démarrer → « PowerShell »),
**sans** « Exécuter en tant qu'administrateur ».

## 1. Installer Git et uv

```powershell
winget install --id Git.Git -e
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Si `winget` n'existe pas** (certains Windows 10) ou échoue : télécharger
l'installeur 64 bits sur <https://git-scm.com/downloads/win> et garder toutes les
options par défaut. S'il exige des droits administrateur qu'on n'a pas, prendre
la version portable (« Portable, thumbdrive edition ») sur la même page,
l'extraire dans `%LOCALAPPDATA%\Programs\Git`, puis ajouter
`%LOCALAPPDATA%\Programs\Git\cmd` au `Path` du compte (menu Démarrer →
« Modifier les variables d'environnement pour votre compte »).

**Si le script d'uv est bloqué** (antivirus, proxy) : télécharger
`uv-x86_64-pc-windows-msvc.zip` dans la dernière version publiée sur
<https://github.com/astral-sh/uv/releases>, copier `uv.exe` et `uvx.exe` dans
`%USERPROFILE%\.local\bin`, puis ajouter ce dossier au `Path` du compte, comme
ci-dessus.

**Fermer et rouvrir PowerShell**, puis vérifier :

```powershell
git --version
uv --version
```

## 2. Récupérer l'outil

```powershell
git clone --branch prod https://github.com/Pierre-Faure/suivi-maintenance-cinema.git C:\suivi-affaires
cd C:\suivi-affaires
uv sync
```

`uv sync` télécharge Python 3.14 et les dépendances exactes du dépôt (`uv.lock`).

Le dossier ne doit pas être dans OneDrive : SQLite y supporte mal la
synchronisation. Si `C:\` est verrouillé sur ce poste, prendre
`%USERPROFILE%\suivi-affaires`, qui n'est pas synchronisé, et adapter les
chemins de ce guide.

## 3. Créer la base et le compte

```powershell
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

`createsuperuser` demande un identifiant, une adresse email (facultative :
Entrée) et le mot de passe deux fois. L'utilisateur choisit son mot de passe
lui-même. Si Django le trouve trop simple, il demande confirmation (`y` pour
le garder).

La base, la clé secrète, les sauvegardes et le journal sont dans
`C:\suivi-affaires\data\`, jamais touché par les mises à jour.

## 4. Créer l'icône du bureau

1. Dans l'Explorateur, clic droit sur `C:\suivi-affaires\lancer.cmd` →
   **Envoyer vers → Bureau (créer un raccourci)** (sous Windows 11 : d'abord
   « Afficher plus d'options »).
2. Clic droit sur le raccourci → **Propriétés** :
   - **Exécuter : Réduite** ;
   - **Changer d'icône**, au choix ;
   - le renommer « Suivi des affaires ».

## 5. Premier lancement

Double-cliquer sur l'icône. Attendu :

- une fenêtre réduite « Suivi des affaires » dans la barre des tâches ;
- le navigateur s'ouvre sur la page de connexion (sinon : <http://127.0.0.1:8000/>) ;
- la fenêtre indique « Première utilisation : pas encore de base à sauvegarder. »

Se connecter avec le compte créé à l'étape 3.

Fermer la fenêtre réduite arrête l'outil. Un second double-clic pendant que
l'outil tourne ouvre simplement le navigateur.

## 6. Régler la racine des documents

Menu **Réglages** :

- **Racine des documents** : le chemin noté au départ, par exemple `Z:\Bâtiment`.
  Un chemin copié depuis l'Explorateur (« Copier en tant que chemin d'accès »,
  entre guillemets) est accepté.
- **Dossier technique** : laisser `_Suivi des affaires`, sauf s'il existe déjà
  un dossier de ce nom avec un autre usage.

Enregistrer. La page doit afficher « Racine accessible : N dossiers ».

## 7. Saisir les entreprises et les rattacher à leurs dossiers

L'annuaire d'un poste neuf est vide. Saisir avec l'utilisateur les entreprises
avec lesquelles il travaille le plus (menu **Annuaire**). Sur la fiche de chaque
entreprise :

- si un dossier du partage porte un nom proche, l'outil le propose : **Rattacher** ;
- sinon : **Choisir le dossier**, dans la liste des dossiers libres de la racine.

Les autres entreprises se rattacheront au fil de l'eau, de la même façon. La
page Réglages indique combien d'entreprises sont rattachées.

## 8. Contrôle final

1. **Fermer** la fenêtre de l'outil, puis le **relancer** par l'icône. La fenêtre
   doit afficher « Sauvegarde : … » puis « Copie sur le partage : … », et
   `Z:\Bâtiment\_Suivi des affaires\sauvegardes\` contenir une copie. (La copie
   sur le partage n'a lieu qu'à partir du lancement qui suit le réglage de la
   racine.)
2. **Mises à jour** : dans PowerShell,

   ```powershell
   git -C C:\suivi-affaires pull --ff-only
   ```

   doit répondre « Already up to date. » sans demander d'identifiant. C'est ce
   que fait le lanceur à chaque ouverture.
3. Sur la fiche d'une affaire de test, **Importer des fichiers** puis ouvrir le
   fichier importé : il doit s'ouvrir dans son application Windows. Supprimer
   ensuite l'affaire de test (le fichier, lui, reste sur le partage).

## Mettre en production une nouvelle version

Depuis le poste de développement :

```powershell
git push origin main:prod
```

Le poste récupère la version au lancement suivant ; le lanceur sauvegarde la
base avant d'appliquer les migrations.

## Dépannage

| Symptôme | Cause probable et solution |
|---|---|
| `'uv'` ou `'git' n'est pas reconnu` dans la fenêtre du lanceur | Le bureau n'a pas encore pris en compte le nouveau `Path` : fermer la session Windows et se reconnecter |
| « Mise à jour impossible » | Pas d'Internet, ou GitHub bloqué. L'outil démarre avec la version en place. Tester `git -C C:\suivi-affaires pull --ff-only` à la main pour voir l'erreur |
| « Racine des documents introuvable » | Partage non connecté, ou outil lancé en administrateur (les lecteurs réseau de la session ne sont alors pas visibles). Ne jamais utiliser « Exécuter en tant qu'administrateur » |
| Le navigateur ne s'ouvre pas | Ouvrir <http://127.0.0.1:8000/> à la main. Le détail du lancement est dans `C:\suivi-affaires\data\lanceur.log` |
| « La base n'a pas pu être mise à jour » | Échec des migrations : l'outil ne démarre pas. Envoyer `data\lanceur.log` au développeur ; les sauvegardes sont dans `data\sauvegardes\` |
| Mot de passe oublié | `cd C:\suivi-affaires` puis `uv run python manage.py changepassword <identifiant>` |
