# Kurzbefehl „Zur Möbel-App“ (iPad, Safari)

Mit diesem Kurzbefehl legst du ein Item aus jeder Produktseite an, die du in Safari geöffnet hast:
**Teilen → Zur Möbel-App**. Der Kurzbefehl liest die Seite in Safari aus und schickt den Inhalt an das
Backend. Das Backend fragt den Shop dabei nicht selbst, deshalb funktioniert es auch bei Shops, die
automatische Abrufe blockieren. Nur die Bilder lädt das Backend selbst herunter.

## 1. Import-Schlüssel im Backend einrichten (einmalig, auf dem Pi)

1. Schlüssel erzeugen:
   ```bash
   openssl rand -hex 24
   ```
2. In `backend/.env` eine Zeile ergänzen:
   ```
   IMPORT_KEY=<der erzeugte Schlüssel>
   ```
3. Backend neu starten (`Strg+C`, dann `./start.sh`). Der Schlüssel wird nur beim Start gelesen.

## 2. iPad vorbereiten (einmalig)

**Einstellungen → Apps → Kurzbefehle → Erweitert → „Skripte ausführen erlauben“** einschalten.
(Bei älteren iPadOS-Versionen: Einstellungen → Kurzbefehle → Erweitert.)

## 3. Kurzbefehl anlegen (einmalig)

1. App **Kurzbefehle** öffnen, oben rechts **+**.
2. Oben auf den Namen tippen, **„Zur Möbel-App“** eingeben.
3. Unten auf **ⓘ** (Details) tippen, **„Im Share-Sheet anzeigen“** einschalten.
   Danach oben im Kurzbefehl auf **„Beliebige Eingabe“** tippen und nur **„Safari-Webseiten“** auswählen.
4. Aktion **„JavaScript auf Webseite ausführen“** hinzufügen. Als Eingabe muss
   **„Kurzbefehleingabe“** stehen. Den vorhandenen Beispielcode löschen und den Code aus
   Abschnitt 4 einfügen.
5. Aktion **„Inhalte von URL abrufen“** hinzufügen:
   - URL: `https://raspberrypi.tail3ed2e1.ts.net/import/page`
   - auf **„Mehr anzeigen“** tippen
   - Methode: **POST**
   - Header hinzufügen: Schlüssel `Content-Type`, Text `application/json`
   - Header hinzufügen: Schlüssel `X-Import-Key`, Text: dein Schlüssel aus Schritt 1
   - Anfragetext (Request Body): **Datei**, dann als Datei die Variable
     **„JavaScript-Ergebnis“** auswählen
6. Aktion **„Wörterbuchwert abrufen“** hinzufügen: Wert für Schlüssel `message`
   in **„Inhalte von URL“**.
7. Aktion **„Mitteilung anzeigen“** hinzufügen, als Text die Variable **„Wörterbuchwert“**.
8. Optional: Aktion **„URL öffnen“** mit `https://dogtype.github.io/furniture_inventory/`,
   dann öffnet sich nach dem Import die App.

## 4. Code für „JavaScript auf Webseite ausführen“

```javascript
// Möbel-App: liest die Produktseite aus und gibt sie an den Kurzbefehl zurück
var esc = function (s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
};
var parts = ["<title>" + esc(document.title) + "</title>"];
document.querySelectorAll("meta[property], meta[name]").forEach(function (m) { parts.push(m.outerHTML); });
document.querySelectorAll('script[type="application/ld+json"]').forEach(function (s) { parts.push(s.outerHTML); });
var isAmazon = /(^|\.)amazon\./.test(location.hostname);
var seen = {};
var addImage = function (src) {
  if (src && src.indexOf("http") === 0 && !seen[src]) {
    seen[src] = true;
    parts.push('<img data-import-image src="' + esc(src) + '">');
  }
};
var bigImages = Array.prototype.filter.call(document.images, function (img) {
  return img.naturalWidth >= 400 && img.naturalHeight >= 400;
});
if (isAmazon) {
  // Amazon: Titel, Preis und Bilder des Produkts, nicht die des Warenkorbs und der Empfehlungen
  var title = document.getElementById("productTitle");
  if (title) parts.push("<h1>" + esc(title.innerText.trim()) + "</h1>");
  var price = document.querySelector(
    "#corePrice_feature_div .a-offscreen, #corePriceDisplay_desktop_feature_div .a-offscreen, " +
    "#apex_desktop .a-offscreen, #centerCol .a-price .a-offscreen, #ppd .a-price .a-offscreen");
  if (price) parts.push("<span data-import-price>" + esc(price.textContent) + "</span>");
  document.querySelectorAll("#imgTagWrapperId img, #main-image-container img, #altImages img").forEach(function (img) {
    var src = img.currentSrc || img.src;
    if (src.indexOf("/images/I/") > -1 && src.indexOf("play-button") < 0) addImage(src.replace(/\._[A-Za-z0-9_,]+_\./, "."));
  });
  if (!parts.some(function (p) { return p.indexOf("data-import-image") > -1; }) && bigImages[0]) {
    addImage(bigImages[0].currentSrc || bigImages[0].src);
  }
} else {
  var h1 = document.querySelector("h1");
  if (h1) parts.push("<h1>" + esc(h1.innerText.trim()) + "</h1>");
  bigImages.forEach(function (img) { addImage(img.currentSrc || img.src); });
}
parts.push("<div>" + esc((document.body.innerText || "").slice(0, 50000)) + "</div>");
completion(JSON.stringify({ url: location.href, html: parts.join("\n") }));
```

## 5. Benutzen

Produktseite in Safari öffnen → **Teilen** → **Zur Möbel-App**. Beim ersten Mal pro Shop fragt das
iPad, ob der Kurzbefehl auf die Seite zugreifen darf. Danach erscheint eine Mitteilung, z. B.
„Importiert: Samt-Sessel Cori (9 von 9 Bildern)“, oder eine Fehlermeldung.

## Testen am PC (ohne iPad)

Um zu prüfen, ob ein Shop funktioniert, kann man denselben Code am PC ausführen und das Ergebnis
als Datei speichern:

1. Produktseite im Browser öffnen, **F12** drücken, Reiter **Konsole**.
2. Den Code aus Abschnitt 4 einfügen, aber die letzte Zeile (`completion(...)`) durch diese ersetzen
   und Enter drücken:
   ```javascript
   var a = document.createElement("a");
   a.href = URL.createObjectURL(new Blob([JSON.stringify({ url: location.href, html: parts.join("\n") })], { type: "application/json" }));
   a.download = "import-" + location.hostname + ".json";
   document.body.appendChild(a); a.click();
   ```
3. Der Browser lädt eine Datei `import-<shop>.json` herunter. Sie enthält nur, was der Kurzbefehl
   auch schicken würde.

Mit `?dry_run=true` an der Adresse (`/import/page?dry_run=true`) zeigt das Backend nur an, was es
erkannt hat, und legt nichts an.
