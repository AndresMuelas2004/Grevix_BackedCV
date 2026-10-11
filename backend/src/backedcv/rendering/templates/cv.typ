// ATS-safe CV: one column, plain text, no tables, images, framed boxes or headers.
// The rules and the grey text are drawing and colour only: the words stay in one column, in order.
// The document arrives as JSON in sys.inputs.data (see pdf_writer.py). Strings are
// inserted as plain text, so special characters need no escaping.

#let cv = json(bytes(sys.inputs.data))
#let name = cv.contact.name
#let muted = rgb("#566170") // the app's muted text colour, also used for the rules

// Consecutive bullets of one entry become one list, so they share a single spacing.
#let group-rows(rows) = {
  let groups = ()
  for row in rows {
    let previous = groups.at(groups.len() - 1, default: none)
    if row.kind == "bullet" and previous != none and previous.kind == "bullet" {
      groups = groups.slice(0, -1) + ((kind: "bullet", texts: previous.texts + (row.text,)),)
    } else {
      groups.push((kind: row.kind, texts: (row.text,)))
    }
  }
  groups
}

#set document(title: if name != none { name } else { "CV" })
#set page(paper: "a4", margin: 0.7in)
#set text(font: "Libertinus Serif", size: 10.5pt, ligatures: false, hyphenate: false)
#set par(leading: 0.6em, spacing: 0.6em)
#set smartquote(enabled: false)
#set list(marker: [•], indent: 0.8em, body-indent: 0.5em)

#if name != none [
  #block(below: 0.6em)[#text(size: 18pt, weight: "bold")[#name]]
]

#if cv.contact.headline != none [
  #par[#cv.contact.headline]
]

// Each detail sits in its own unbreakable box, and the boxes are separated by horizontal space
// only, with no separator character. A long line breaks in that gap, so a wrapped line never ends
// with a stray bar. Blank details are skipped.
#let details = cv.contact.details.filter(detail => detail.trim() != "")
#if details.len() > 0 [
  #block(above: 0.5em)[
    #text(fill: muted)[#details.map(detail => box[#detail]).join(h(1.2em))]
  ]
]

#for section in cv.sections [
  // A thin rule sits under each heading. The space above a heading separates the sections.
  #if section.heading != "" [
    #block(above: 1.2em, below: 0.7em, sticky: true)[
      #stack(
        dir: ttb,
        spacing: 0.3em,
        text(size: 11.5pt, weight: "bold")[#section.heading],
        line(length: 100%, stroke: 0.5pt + muted),
      )
    ]
  ]
  // The lines of one entry sit close together; every entry after the first gets the same gap.
  #for (index, item) in section.items.enumerate() [
    #if index > 0 [#v(1em, weak: true)]
    #for group in group-rows(item.lines) [
      #if group.kind == "bullet" [
        #list(..group.texts)
      ] else [
        #par[#group.texts.first()]
      ]
    ]
  ]
]
