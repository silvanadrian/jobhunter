# Dokumente (Arbeitszeugnisse, Diplome)

Dieser Ordner ist standardmässig von Git **ausgeschlossen** (siehe `.gitignore`).
Arbeitszeugnisse und Diplome bleiben so nur auf deinem Computer.

Willst du sie im (privaten!) Repository speichern, um sie an Bewerbungen
anzuhängen:

1. In `jobhunter.yml` `documents: {store_certificates: true}` setzen.
2. Datei bewusst hinzufügen: `git add -f profile/dokumente/arbeitszeugnis-2024.pdf`
3. In `applications/<slug>/application.md` unter `attach:` eintragen.

Nie hier ablegen: Ausweis- oder Passkopien, AHV-Nummer, Bankangaben.
