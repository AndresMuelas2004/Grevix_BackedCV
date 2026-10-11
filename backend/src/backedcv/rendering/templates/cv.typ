// ATS-safe CV: one column, plain text, no tables, images, boxes or headers.
// The document arrives as JSON in sys.inputs.data (see pdf_writer.py). Strings are
// inserted as plain text, so special characters need no escaping.

#let cv = json(bytes(sys.inputs.data))
#let name = cv.contact.name

#set document(title: if name != none { name } else { "CV" })
#set page(paper: "a4", margin: 0.7in)
#set text(font: "Libertinus Serif", size: 10.5pt, ligatures: false, hyphenate: false)
#set par(leading: 0.6em, spacing: 0.6em)
#set smartquote(enabled: false)
#set list(marker: [•], indent: 0.8em, body-indent: 0.5em)

#if name != none [
  #block(below: 0.3em)[#text(size: 14pt, weight: "bold")[#name]]
]

#if cv.contact.details.len() > 0 [
  #par[#cv.contact.details.join(" | ")]
]

#for section in cv.sections [
  #if section.heading != "" [
    #block(above: 0.9em, below: 0.4em, sticky: true)[#text(weight: "bold")[#section.heading]]
  ]
  #for (index, item) in section.items.enumerate() [
    #if index > 0 [#v(0.5em)]
    #for line in item.lines [
      #if line.kind == "bullet" [
        #list[#line.text]
      ] else [
        #par[#line.text]
      ]
    ]
  ]
]
