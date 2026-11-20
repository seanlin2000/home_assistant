# Clean Code Conventions

Coding conventions for this project, distilled from *Clean Code* by Robert C. Martin, Chapters 2 (Meaningful Names), 3 (Functions), and 4 (Comments). Examples are written in Python to match the project.

---

## 1. Meaningful Names

A name should answer three questions: why does this exist, what does it do, and how is it used. If a name needs a comment to explain it, the name has failed.

### 1.1 Reveal intent

```python
# Bad
d = 5  # elapsed time in days

# Good
elapsed_time_in_days = 5
```

Name magic numbers, indices, and status values so readers do not have to infer context.

```python
# Bad
def get_them(the_list):
    return [x for x in the_list if x[0] == 4]

# Good
def get_flagged_cells(game_board):
    return [cell for cell in game_board if cell.is_flagged()]
```

### 1.2 Avoid disinformation

- Do not call something `account_list` unless it is actually a list. Prefer `accounts`.
- Avoid names that differ only subtly (`XYZControllerForEfficientHandlingOfStrings` vs `XYZControllerForEfficientStorageOfStrings`).
- Never use lowercase `l` or uppercase `O` as variable names.

### 1.3 Make meaningful distinctions

Names that differ must mean different things.

- No number series: `a1`, `a2` say nothing. Use `source`, `destination`.
- No noise words: `ProductInfo` and `ProductData` are indistinguishable from `Product`. Words like `variable`, `data`, `info`, `object`, `the_` add nothing.

### 1.4 Use pronounceable and searchable names

- Names are spoken in discussion. `generation_timestamp` beats `genymdhms`.
- Names are grepped. `MAX_CLASSES_PER_STUDENT` is findable; the literal `7` is not.
- Single-letter names are acceptable only as loop counters in very short scopes. **Name length should grow with scope size.**

### 1.5 Avoid encodings

- No Hungarian notation (`str_name`, `i_count`). The type system already tracks types.
- No member prefixes (`m_`, `_the`) beyond Python's conventional single leading underscore for private members.
- Do not encode "interface" or "abstract" into names (`IShapeFactory`). If one side must be marked, mark the implementation.

### 1.6 Avoid mental mapping

Readers should not have to translate `r` into "the URL without host and scheme." Use the actual concept name. Clarity is king.

### 1.7 Classes are nouns, functions are verbs

- Classes: `Customer`, `WikiPage`, `AddressParser`. Avoid `Manager`, `Processor`, `Data`, `Info` in class names.
- Functions: `post_payment`, `delete_page`, `save`.
- Accessors and predicates: `get_name()`, `set_name()`, `is_posted()`.
- Prefer descriptive factory functions over overloaded constructors: `Complex.from_real_number(23.0)` over `Complex(23.0)`.

### 1.8 Don't be cute, don't pun

- Choose clarity over humour: `delete_items()` not `holy_hand_grenade()`.
- **Pick one word per concept** and stick with it. Do not mix `fetch`, `retrieve`, and `get` for the same idea across modules.
- Do not reuse a word for a different meaning. If `add` means arithmetic addition elsewhere, call the collection operation `insert` or `append`.

### 1.9 Choose the right domain

- Prefer solution-domain names (algorithm names, pattern names, CS terms) that programmers already know: `JobQueue`, `AccountVisitor`.
- Fall back to problem-domain names when no programmer term exists, so a domain expert can be consulted.

### 1.10 Add meaningful context, not gratuitous context

- Group related variables (`first_name`, `street`, `zipcode`) into a class such as `Address` rather than prefixing each with `addr_`.
- Do not prefix every class with an application acronym. Shorter names are better as long as they are clear.

### 1.11 Rename freely

Modern tools make renaming cheap. When a better name appears, use it.

---

## 2. Functions

### 2.1 Small, then smaller

- Functions should rarely exceed 20 lines.
- Blocks inside `if`, `else`, `while`, and `for` should be one line long, ideally a function call with a descriptive name.
- Indentation depth should not exceed one or two levels.

### 2.2 Do one thing

> Functions should do one thing. They should do it well. They should do it only.

A function does one thing when every statement in it sits **one level of abstraction below the function's name**. Two tests:

1. If you can extract another function whose name is not merely a restatement of its body, the original does more than one thing.
2. If the function naturally divides into sections (declarations, initialisation, main loop, cleanup), it does more than one thing.

### 2.3 One level of abstraction per function: the Stepdown Rule

Code should read top to bottom like a narrative. Each function is followed by the functions at the next level of abstraction, so the module reads as a series of "TO do X, we do A, then B, then C" paragraphs. Never mix high-level calls (`render_page()`) with low-level details (`buffer.append("\n")`) in the same function.

### 2.4 Avoid switch statements and long if/elif chains

They inherently do N things and violate the Single Responsibility and Open/Closed principles. Tolerate them only when they appear once, create polymorphic objects, and are hidden behind an abstraction (e.g. a factory). Dispatch behaviour through polymorphism instead.

### 2.5 Use descriptive names

- A long descriptive name beats a short enigmatic one, and beats a descriptive comment.
- Try several names and read the code with each. Hunting for a good name often improves the design.
- Be consistent in phrasing across related functions: `include_setup_pages`, `include_suite_setup_page`, `include_setup_page`.

### 2.6 Function arguments

| Arity | Guidance |
|-------|----------|
| 0 | Ideal |
| 1 | Good |
| 2 | Acceptable, comes at a cost |
| 3 | Avoid where possible |
| 4+ | Requires special justification, and then still avoid |

- **Single-argument forms:** asking a question about the argument (`file_exists(path)`), transforming it into a return value (`open_file(path)`), or handling an event (`password_attempt_failed_n_times(attempts)`). Avoid other monadic shapes.
- **No flag arguments.** A boolean parameter announces that the function does two things. Split it: `render_for_suite()` and `render_for_single_test()` instead of `render(is_suite)`.
- **Two arguments** are fine when they are ordered parts of one value (`Point(x, y)`). Otherwise reduce to one by making one argument a member of the class or extracting a new class.
- **Argument objects.** When a function needs more than two or three arguments, some of them belong together in their own class: `make_circle(center, radius)` over `make_circle(x, y, radius)`.
- **Variadic arguments** count as one argument of type list. `format(template, *args)` is dyadic.
- **Verbs and keywords.** A function and its argument should form a verb/noun pair (`write_field(name)`). Encoding argument names into the function name removes ordering confusion: `assert_expected_equals_actual(expected, actual)`.
- **No output arguments.** If a function must change state, it should change the state of its owning object: `report.append_footer()` not `append_footer(report)`.
- Project rule: **every parameter must have a type annotation.** Ask the user when the type is unclear.

### 2.7 Have no side effects

A function named `check_password` must not also initialise a session. Hidden side effects create temporal couplings and order dependencies. If a coupling is unavoidable, put it in the name.

### 2.8 Command-query separation

A function either changes state or returns information about state, never both.

```python
# Bad
if set_attribute("username", "unclebob"): ...

# Good
if attribute_exists("username"):
    set_attribute("username", "unclebob")
```

### 2.9 Prefer exceptions to error codes

- Returned error codes force the caller to handle errors immediately and produce deeply nested code.
- Extract the bodies of `try` and `except` blocks into their own functions.
- **Error handling is one thing.** If a function contains `try`, it should be the first statement, and nothing should follow the `except`/`finally` blocks.

```python
def delete(page: Page) -> None:
    try:
        delete_page_and_all_references(page)
    except Exception as error:
        log_error(error)
```

### 2.10 Don't repeat yourself

Duplication bloats code and multiplies the places a change must be made. Project rule: reuse existing functions, and when shared logic is needed across files, move it to `utils/{util_type}_utils.py`.

### 2.11 Structured programming rules relax for small functions

Multiple `return` statements, `break`, and `continue` are fine in tiny functions and can be more expressive than single-exit discipline.

### 2.12 How to get there

Write the rough draft first, cover it with tests, then refactor: split functions, rename, remove duplication, shrink and reorder. Nobody writes clean functions on the first pass.

---

## 3. Comments

> "Don't comment bad code, rewrite it." (Kernighan and Plauger)

Comments compensate for a failure to express intent in code. They drift from the code they describe and end up lying. The only truly good comment is the one you found a way not to write.

### 3.1 Comments do not make up for bad code

When tempted to comment a confusing block, clean the block instead. Most intent can be expressed by extracting a well-named function or variable.

```python
# Bad
# Check to see if the employee is eligible for full benefits
if (employee.flags & HOURLY_FLAG) and employee.age > 65: ...

# Good
if employee.is_eligible_for_full_benefits(): ...
```

### 3.2 Acceptable comments

| Kind | Example |
|------|---------|
| Legal | Copyright or license header, ideally pointing to an external document |
| Informative | Describing the format a regex matches, when a better name is not available |
| Explanation of intent | Why a decision was made, not what the code does |
| Clarification | Translating obscure values from library code you cannot change |
| Warning of consequences | "Not thread safe, create a new instance each time" |
| TODO | Work that should be done but cannot be done now. Never an excuse for bad code. Review and remove regularly. |
| Amplification | Flagging something that looks unimportant but is critical |
| Public API docs | Docstrings for genuinely public interfaces |

### 3.3 Bad comments

- **Mumbling:** comments that only make sense to the author.
- **Redundant:** restating what the code already says, often less precisely.
- **Misleading:** imprecise wording that sets wrong expectations.
- **Mandated:** rules that every function or variable must have a docstring. These produce clutter and lies.
- **Journal comments and bylines:** version control tracks who changed what and when.
- **Noise:** `# Default constructor`, `# Returns the day of the month`.
- **Position markers and banners:** `# ---- Actions ----`. Use very sparingly, if ever.
- **Closing-brace or end-of-block comments:** shorten the function instead.
- **Commented-out code:** delete it. Version control remembers it.
- **HTML in comments.**
- **Nonlocal information:** describing behaviour controlled elsewhere in the system.
- **Too much information:** historical essays and RFC excerpts.
- **Inobvious connection:** a comment that itself needs explaining.
- **Function headers on short functions:** a good name is better.
- **Docstrings on nonpublic code:** formality without benefit.

### 3.4 Project rule on comments and docstrings

Prefer expressive names and small functions over comments. When a comment is warranted, it should explain **why**, not **what**. Keep every comment adjacent to the code it describes, and delete it when the code changes.
