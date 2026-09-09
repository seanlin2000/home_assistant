# Diagram legend

Every diagram in this handbook uses the same four colours and one highlight. The colour says who is responsible for a box: blue is code written in this repository, grey is software the project runs but did not write, green is a physical device, and red is anything whose traffic leaves the apartment.

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
a("our code:<br/>written in this repository")
b("third-party software<br/>we run and configure")
c("a physical device")
d("traffic that leaves<br/>the apartment")
e("the part this page<br/>is about")
class a ours
class b third
class c hw
class d ext
class e third
class e current
```

Position carries meaning as well. A diagram reads top to bottom or left to right, and each band is one layer: a tier of the system in an architecture drawing, or one stage in a pipeline. Bands span the full drawing with their titles at the left, a box sits in the band below, or the column after, whatever calls it, and every arrow points in the reading direction.

Shapes carry meaning too, and there are four. A rounded rectangle is anything that runs: a process, a service, a device, or an external API, told apart by colour. A cylinder is a data store such as a file, a database, or a log. A diamond is a decision in a chain of rules. A stadium, the shape with fully round ends, is something a person says or does.

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
subgraph runs["runs"]
  r("a process, service,<br/>device, or API")
end
subgraph stores["stores"]
  s[("a file, database,<br/>cache, or log")]
end
subgraph decides["decides"]
  d{"a rule in a chain"}
end
subgraph person["a person"]
  p(["what you say or do"])
end
r --> s --> d --> p
class r,s,d third
```

The system map on every page's "Where this fits" is one drawing, `operator_manual/_includes/system_map.mmd`, included by reference. Only the highlight changes from page to page. The rules behind all of this are in the repository's `draw-diagram` skill.
