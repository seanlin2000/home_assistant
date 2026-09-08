# Diagram legend

Every diagram in this manual uses the same four colours and one highlight.

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
a["our code:<br/>written in this repository"]
b["third-party software<br/>we run and configure"]
c[["a physical device"]]
d>"traffic that leaves<br/>the apartment"]
e["the part this page<br/>is about"]
class a ours
class b third
class c hw
class d ext
class e third
class e current
```

Shapes carry meaning too: a rectangle is a process or service, a double-edged rectangle is a device, a cylinder is a data store, a diamond is a decision, a rounded box is something a person says or does, and a flag is an external API.

The system map on every page's "Where this fits" is one drawing, `operator_manual/_includes/system_map.mmd`, included by reference. Only the highlight changes from page to page.
