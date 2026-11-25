// Gemeinsame Gestaltung für Lebenslauf und Motivationsschreiben.
//
// Drei Stile, wählbar unter `style:` in profile/cv.yaml (pro Variante
// überschreibbar):
//   klassisch  angelehnt an Awesome CV (A4, Roboto + Source Sans 3,
//              Akzentfarbe für die ersten drei Buchstaben jedes Abschnittstitels)
//   schlicht   schwarz/grau, Abschnittstitel in Kapitälchen mit feiner Linie
//   kompakt    wie klassisch, aber kleinere Schrift und engere Abstände
// Eigene Umsetzung in Typst, ohne Code aus Awesome CV und ohne externe Pakete.
//
// Daten: profile/cv.yaml (Basis) plus optional eine Variante
// applications/<slug>/cv.yaml, übergeben mit `--input variant=/pfad/cv.yaml`.

#let header-font = "Roboto"
#let body-font = "Source Sans 3"

#let labels = (
  de: (summary: "Profil", experience: "Berufserfahrung", education: "Ausbildung",
       skills: "Kenntnisse", languages: "Sprachen", cv: "Lebenslauf",
       letter: "Motivationsschreiben"),
  en: (summary: "Summary", experience: "Experience", education: "Education",
       skills: "Skills", languages: "Languages", cv: "CV", letter: "Cover Letter"),
)

// --- Quellen laden -------------------------------------------------------------

#let load-sources() = {
  let base = yaml(sys.inputs.at("profile", default: "/profile/cv.yaml"))
  let path = sys.inputs.at("variant", default: "")
  let v = if path != "" { yaml(path) } else { (:) }
  if v == none { v = (:) }
  (base, v)
}

// --- Stil ----------------------------------------------------------------------

#let default-accent = "#0084B8"

// Masse und Farben pro Stil. «klassisch» entspricht exakt dem bisherigen Aussehen.
#let classic = (
  section-kind: "accent",
  darktext: rgb("#414141"), text-col: rgb("#333333"),
  graytext: rgb("#5D5D5D"), lighttext: rgb("#999999"),
  margin: (left: 1.4cm, right: 1.4cm, top: 0.8cm, bottom: 1.8cm),
  body-size: 9pt, leading: 0.5em, par-spacing: 0.6em,
  name-size: 32pt, position-size: 7.6pt, address-size: 8pt, social-size: 6.8pt,
  photo-size: 2.6cm, header-gap: 4mm,
  section-size: 16pt, section-above: 4mm, section-below: 2.5mm,
  org-size: 10pt, location-size: 9pt, title-size: 8pt,
  entry-below: 3.2mm, entry-gutter: 2.6mm, bullets-gap: 2.2mm,
  bullet: "•", list-spacing: 0.5em,
  skill-cat-size: 10pt, skill-inset: 0.3em,
  letter-size: 10pt,
)

#let themes = (
  klassisch: classic,
  schlicht: (..classic,
    section-kind: "rule",
    section-size: 12pt, section-below: 2.8mm,
    bullet: "–",
  ),
  kompakt: (..classic,
    margin: (left: 1.2cm, right: 1.2cm, top: 0.7cm, bottom: 1.5cm),
    body-size: 8.5pt, leading: 0.45em, par-spacing: 0.5em,
    name-size: 26pt, position-size: 7.4pt, address-size: 7.6pt, social-size: 6.6pt,
    photo-size: 2.2cm, header-gap: 2.5mm,
    section-size: 13pt, section-above: 2.6mm, section-below: 1.8mm,
    org-size: 9.5pt, location-size: 8.5pt, title-size: 7.6pt,
    entry-below: 2.2mm, entry-gutter: 1.9mm, bullets-gap: 1.4mm,
    list-spacing: 0.4em,
    skill-cat-size: 9pt, skill-inset: 0.2em,
    letter-size: 9.5pt,
  ),
)

#let resolve-style(base, v) = {
  let merged = (:)
  for (where, src) in (("profile/cv.yaml", base), ("Variante", v)) {
    let s = src.at("style", default: none)
    if s == none { continue }
    if type(s) != dictionary {
      panic("style: in " + where + " muss ein Block mit theme, accent und photo sein")
    }
    for (key, value) in s {
      if key not in ("theme", "accent", "photo") {
        panic("style: unbekannter Schlüssel «" + key + "» in " + where
          + " (erlaubt: theme, accent, photo)")
      }
      merged.insert(key, value)
    }
  }

  let theme = merged.at("theme", default: "klassisch")
  if type(theme) != str or lower(theme.trim()) not in themes {
    let shown = if type(theme) == str { theme } else { repr(theme) }
    panic("style.theme: ungültiger Stil «" + shown + "». Erlaubt sind klassisch, schlicht und kompakt.")
  }
  theme = lower(theme.trim())

  let accent = merged.at("accent", default: default-accent)
  if accent == none {
    panic("style.accent ist leer. Hex-Farben in Anführungszeichen setzen, "
      + "z. B. accent: \"#0084B8\" (ohne Anführungszeichen gilt # als Kommentar).")
  }
  if type(accent) != str or accent.trim().match(regex("^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")) == none {
    panic("style.accent: ungültige Farbe " + repr(accent)
      + ". Erwartet wird eine Hex-Farbe wie \"#0084B8\" oder \"#08B\".")
  }

  let photo = merged.at("photo", default: true)
  if type(photo) != bool {
    panic("style.photo muss true oder false sein, nicht " + repr(photo) + ".")
  }

  let t = themes.at(theme)
  // Bei «schlicht» gibt es keine Farbakzente: die Akzentfarbe wird ignoriert.
  let accent-col = if theme == "schlicht" { t.graytext } else { rgb(accent.trim()) }
  (..t, name: theme, accent: accent-col, photo: photo)
}

#let st = resolve-style(..load-sources())

// Kurznamen, die cv.typ und letter.typ verwenden.
#let accent = st.accent
#let darktext = st.darktext
#let text-col = st.text-col
#let graytext = st.graytext
#let lighttext = st.lighttext

// --- Daten laden und Variante auflösen ---------------------------------------

#let load-data() = {
  let (base, v) = load-sources()

  // Punkte der Basis nach ID, damit eine Variante sie nur nennen muss.
  let index = (:)
  for role in base.experience {
    for b in role.at("bullets", default: ()) { index.insert(b.id, b) }
  }
  let resolve(b) = if type(b) == str {
    assert(b in index, message: "Variante nennt unbekannten Punkt " + b)
    index.at(b)
  } else { b }

  let experience = if "experience" in v {
    v.experience.map(e => {
      let matches = base.experience.filter(r => r.id == e.role)
      assert(matches.len() == 1, message: "Variante nennt unbekannte Rolle " + e.role)
      let r = matches.first()
      let bullets = e.at("bullets", default: r.at("bullets", default: ()))
      (..r, bullets: bullets.map(resolve))
    })
  } else { base.experience }

  let person = base.person
  if "position" in v { person.insert("position", v.position) }
  (
    lang: v.at("lang", default: base.at("lang", default: "de")),
    person: person,
    summary: v.at("summary", default: base.at("summary", default: none)),
    experience: experience,
    education: v.at("education", default: base.at("education", default: ())),
    skills: v.at("skills", default: base.at("skills", default: ())),
    languages: v.at("languages", default: base.at("languages", default: ())),
    sections: v.at("sections", default: base.at("sections",
      default: ("summary", "experience", "education", "skills", "languages"))),
    letter: v.at("letter", default: none),
    style: st,
  )
}

// --- Symbole (Font Awesome 6 Free, SIL OFL 1.1, siehe fonts/) ----------------

#let fa-solid = "Font Awesome 6 Free Solid"
#let fa-brands = "Font Awesome 6 Brands"
#let fa(font, code) = text(font: font, weight: if font == fa-solid { 900 } else { 400 }, fill: text-col, code)

#let icons = (
  phone: fa(fa-solid, "\u{f3ce}"),
  email: fa(fa-solid, "\u{f0e0}"),
  homepage: fa(fa-solid, "\u{e3af}"),
  github: fa(fa-brands, "\u{f092}"),
  linkedin: fa(fa-brands, "\u{f08c}"),
)

// --- Bausteine -----------------------------------------------------------------

#let page-setup(name, kind, body, left-note: "") = {
  set document(title: name + " – " + kind, author: name)
  set page(paper: "a4", margin: st.margin,
    footer: context {
      set text(8pt, font: body-font, fill: lighttext)
      grid(columns: (1fr, auto, 1fr),
        align(left, smallcaps(left-note)),
        smallcaps(name + h(0.6em) + "·" + h(0.6em) + kind),
        align(right, str(counter(page).get().first())))
    })
  set text(font: body-font, size: st.body-size, fill: text-col, lang: "de", hyphenate: true)
  set par(leading: st.leading, spacing: st.par-spacing)
  body
}

#let header(p, align-to: left) = {
  let social = ()
  if p.at("phone", default: "") != "" { social.push((icons.phone, p.phone, "tel:" + p.phone.replace(" ", ""))) }
  if p.at("email", default: "") != "" { social.push((icons.email, p.email, "mailto:" + p.email)) }
  if p.at("homepage", default: "") != "" { social.push((icons.homepage, p.homepage, "https://" + p.homepage)) }
  if p.at("github", default: "") != "" { social.push((icons.github, p.github, "https://github.com/" + p.github)) }
  if p.at("linkedin", default: "") != "" { social.push((icons.linkedin, p.linkedin, "https://www.linkedin.com/in/" + p.linkedin)) }

  let block-content = {
    set par(spacing: 0pt)
    text(st.name-size, font: header-font, weight: "light", fill: graytext, p.at("first_name", default: ""))
    text(st.name-size, font: header-font, weight: "light", " ")
    text(st.name-size, font: header-font, weight: "bold", fill: text-col, p.at("last_name", default: ""))
    v(1.6mm)
    if p.at("position", default: "") != "" {
      text(st.position-size, fill: accent, smallcaps(p.position))
      v(1.2mm)
    }
    if p.at("address", default: "") != "" {
      text(st.address-size, font: header-font, style: "italic", fill: lighttext, p.address)
      v(1.4mm)
    }
    set text(st.social-size, font: header-font, fill: text-col)
    social.map(((icon, label, url)) => box(link(url)[#icon #label]))
      .join(h(1em) + "|" + h(1em))
  }
  // Das Foto übergibt scripts/build-cv.sh nur, wenn profile/foto.jpg existiert;
  // `style.photo: false` blendet es trotzdem aus.
  let photo = sys.inputs.at("photo", default: "")
  if photo != "" and st.photo {
    grid(columns: (st.photo-size, 1fr), column-gutter: 0.5cm, align: horizon,
      image(photo, width: st.photo-size, height: st.photo-size, fit: "cover"),
      block-content)
  } else {
    align(align-to, block-content)
  }
  v(st.header-gap)
}

#let section(title) = {
  v(st.section-above)
  if st.section-kind == "rule" {
    // schlicht: Kapitälchen, leicht gesperrt, feine graue Linie darunter
    block(below: st.section-below, {
      set par(spacing: 0pt)
      text(st.section-size, weight: "semibold", fill: text-col, tracking: 0.06em, smallcaps(title))
      v(1.2mm)
      line(length: 100%, stroke: 0.5pt + lighttext)
    })
  } else {
    let chars = title.clusters()
    block(below: st.section-below, {
      text(st.section-size, weight: "bold", fill: accent, chars.slice(0, calc.min(3, chars.len())).join())
      text(st.section-size, weight: "bold", fill: text-col, chars.slice(calc.min(3, chars.len())).join())
      h(0.3em)
      box(width: 1fr, line(length: 100%, stroke: 0.9pt + graytext))
    })
  }
}

#let entry(org, location, title, dates, bullets: ()) = block(below: st.entry-below, breakable: false, {
  set par(spacing: 0pt)
  grid(columns: (1fr, auto), row-gutter: st.entry-gutter, align: (left, right),
    text(st.org-size, weight: "bold", fill: darktext, org),
    text(st.location-size, weight: "light", style: "italic", fill: accent, location),
    text(st.title-size, fill: graytext, smallcaps(title)),
    text(st.title-size, weight: "light", style: "italic", fill: graytext, dates))
  if bullets.len() > 0 {
    v(st.bullets-gap)
    set text(st.body-size, weight: "light", fill: text-col)
    set list(marker: text(fill: text-col, st.bullet), indent: 0pt, body-indent: 0.7em, spacing: st.list-spacing)
    list(..bullets.map(b => b.text))
  }
})

#let skill-table(rows) = table(
  columns: (auto, 1fr), stroke: none, inset: (x: 0.35em, y: st.skill-inset),
  align: (right + horizon, left + horizon),
  ..rows.map(((cat, items)) => (
    text(st.skill-cat-size, weight: "bold", fill: darktext, cat),
    text(st.body-size, weight: "light", fill: text-col, items))).flatten())
