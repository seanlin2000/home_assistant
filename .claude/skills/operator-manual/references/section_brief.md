# Brief for one section subagent

Fill every `{{placeholder}}`, then launch a `general-purpose` subagent with this text. Attach nothing else; the subagent reads the repository itself.

---

Write `operator_manual/{{file}}` for the Home Assistant Handbook of the repository at `{{repo_root}}`. Work only inside that repository. Write the one file named above and reply with its path plus a list of glossary terms you defined (term and one-sentence definition). Do not edit any other file.

**What the manual is.** A book that teaches someone with a computer science degree, who has never used an LLM API, MCP, Home Assistant, the Wyoming protocol, Docker on macOS, or a UTM virtual machine, how this local-first voice assistant works and how to run each part. It describes the system as built today and never narrates history or departures from the design.

**Read first, in this order.**
1. `.claude/skills/operator-manual/references/section_template.md` (the section profile you must follow exactly), `diagram_style.md`, `system_map.md`, `complexity_rubric.md`.
2. `operator_manual/index.md` for the voice, and `operator_manual/glossary.md` for terms already defined; reuse their wording.
3. Your design doc: `{{design_doc}}`. Read all of it, including the "As built" appendices at the end. Where the body and an appendix or the code disagree, the appendix and the code win.
4. The code: {{code_paths}}.
5. Runnable steps for this part: {{runnable_sources}}.

**Your section.** Number {{number}}, title "{{title}}". Complexity: packages={{packages}} parts={{parts}} concepts={{concepts}} tier={{tier}}; put that comment under the title and respect the tier's budget. Highlight in "Where this fits": `class {{highlight}} current`{{style_line}}.

**Rules.**
- Follow the section profile's headings in order. Every term in "Key definitions" must be in `glossary.md` or in your reply's list of new terms.
- Diagrams: Mermaid only, per `diagram_style.md`; the map block includes the palette through the system map; every other flowchart starts with `--8<-- "_includes/palette.mmd"` and uses only the five classes. Every `###` part under "How it works" opens with a diagram or says in one sentence why none is needed.
- Code samples are copied from the files you read, at most 25 lines, trimmed with `...`, with a caption line above the fence naming the file and symbol.
- "Run it yourself" uses real commands from the sources above and says what the reader will see and how to stop.
- Links to other sections are relative (`04_conversation_agent.md`); links to design docs and source are absolute GitHub URLs under `https://github.com/seanlin2000/home_assistant/blob/main/`.
- Short declarative sentences, second person allowed, no marketing words, no emoji, no bullet walls.
- Before replying, run `uv run manual-check --no-render operator_manual/{{file}}` from the repository root and fix every finding. Then run `uv run manual-check --png {{png_dir}} operator_manual/{{file}}` (renders every diagram; needs `mmdc`), fix every parse error, and open every PNG with the Read tool: each diagram must satisfy the four rules in `diagram_style.md` (layers with meaning, readable labels, nothing dark, tidy edges). Redraw and render again until they all do.
