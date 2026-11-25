// Motivationsschreiben. Liest `letter:` aus der Variante:
//   make letter VARIANT=applications/<slug>
//
// letter:
//   recipient: Contoso AG
//   recipient_address: [Musterweg 2, 8000 Zürich]
//   title: Bewerbung als Senior Software Engineer
//   opening: Sehr geehrte Damen und Herren
//   paragraphs: [{text: ..., evidence: [E1]}]
//   closing: Freundliche Grüsse
//   date: ""          # leer = heutiges Datum

#import "lib.typ": *

#let d = load-data()
#let l = labels.at(d.lang, default: labels.de)
#let name = d.person.at("first_name", default: "") + " " + d.person.at("last_name", default: "")
#let letter = if d.letter == none { (
  recipient: "Firma", recipient_address: (), title: "Bewerbung",
  opening: "Sehr geehrte Damen und Herren",
  paragraphs: ((text: "Dieser Brief hat noch keinen Inhalt: `letter:` in der Variante ausfüllen."),),
  closing: "Freundliche Grüsse") } else { d.letter }

#let today = {
  let t = datetime.today()
  if d.lang == "de" { t.display("[day].[month].[year]") } else { t.display("[day] [month repr:long] [year]") }
}
#let date = letter.at("date", default: "")
#let date = if date == "" or date == none { today } else { date }

#show: page-setup.with(name, l.letter, left-note: date)
#set text(lang: d.lang)

#header(d.person, align-to: right)

#block(below: 6mm, {
  set par(spacing: 1.6mm)
  text(11pt, weight: "bold", fill: darktext, letter.recipient)
  for line in letter.at("recipient_address", default: ()) {
    parbreak()
    text(9pt, fill: graytext, smallcaps(line))
  }
})

#align(right, text(9pt, weight: "light", style: "italic", fill: graytext, date))
#v(4mm)
#text(10pt, weight: "bold", fill: darktext, underline(letter.title))
#v(5mm)

#{
  set text(st.letter-size, weight: "light", fill: graytext)
  set par(justify: true, leading: 0.75em, spacing: 1.1em)
  [#letter.opening]
  parbreak()
  for p in letter.paragraphs { [#p.text]; parbreak() }
  v(3mm)
  [#letter.closing]
  v(8mm)
  text(10pt, weight: "bold", fill: darktext, name)
}
#context [#metadata(counter(page).final().first()) <page-count>]
