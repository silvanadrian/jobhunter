// Lebenslauf. Bauen mit:
//   make cv                                  (Basis aus profile/cv.yaml)
//   make cv VARIANT=applications/<slug>      (Bewerbungsvariante)
// oder direkt:
//   typst compile --root . --font-path fonts --ignore-system-fonts \
//     --input variant=/applications/<slug>/cv.yaml cv/cv.typ out.pdf

#import "lib.typ": *

#let d = load-data()
#let l = labels.at(d.lang, default: labels.de)
#let name = d.person.at("first_name", default: "") + " " + d.person.at("last_name", default: "")

#show: page-setup.with(name, l.cv)
#set text(lang: d.lang)

#header(d.person)

#for s in d.sections {
  if s == "summary" and d.summary != none {
    section(l.summary)
    par(justify: true, text(st.body-size, weight: "light", d.summary.text))
  } else if s == "experience" and d.experience.len() > 0 {
    section(l.experience)
    for r in d.experience {
      entry(r.org, r.location, r.title, r.dates, bullets: r.at("bullets", default: ()))
    }
  } else if s == "education" and d.education.len() > 0 {
    section(l.education)
    for e in d.education {
      entry(e.school, e.at("location", default: ""), e.degree, e.dates,
        bullets: e.at("notes", default: ()).map(n => (text: n)))
    }
  } else if s == "skills" and d.skills.len() > 0 {
    section(l.skills)
    skill-table(d.skills.map(k => (k.category, k.items)))
  } else if s == "languages" and d.languages.len() > 0 {
    section(l.languages)
    skill-table(d.languages.map(k => (k.name, k.level)))
  }
}

// Für die 2-Seiten-Prüfung: typst query cv/cv.typ "<page-count>" --field value --one
#context [#metadata(counter(page).final().first()) <page-count>]
