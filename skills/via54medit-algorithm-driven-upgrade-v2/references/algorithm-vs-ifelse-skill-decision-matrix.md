# Decision Matrix: Algorithm vs If/Else Skill (2026-08-04)

## When the user corrects a repeated mistake, the wrong answer is to make a new skill with `if user_says_X: do_Y` steps.

That violates via54Medit's algorithm-driven principle ("不写死绝对值不塞 memory") and the user will say "集成到算法里" the next turn.

This reference is the decision matrix: do I make a new **skill** (if/else flow) or a new **algorithm** (PageRank+EWMA+Bayesian)?

## Decision matrix

| Symptom in user feedback | Wrong fix (if/else skill) | Right fix (algorithm) |
|---|---|---|
| "I want X, not Y" (location / path) | `if path.startswith('/Users/david/Desktop/雷管方案_PDFs_复现'): replace_with('_literature_citation_index/')` | `project_layout_resolver(role='source_of_truth', intent='cite_for_publication')` → PageRank on `project_layout.json` |
| "I want X, not Y" (action) | `if action == 'A': do_B()` | `medit_decide_correction(project, action)` → Bayesian Beta + fuzzy match on past outcomes |
| "I want X, not Y" (format) | `re.sub(r'pattern', 'replacement', text)` | `medit_parse_instruction(text)` → Self-Consistency 3-vote + heuristic fallback |
| Same correction needed 3+ times in a session | write it down as a constraint | feed it into trainset via `medit_record_outcome` |
| Wants deterministic behavior across devices | `assert some_condition` | `atomic_write(state.json, dedup_by_hash(input))` |
| Wants LLM-driven flexibility | `if/elif/else` tree | `parse_instruction(n_votes=3, fallback=heuristic)` |

## The 3-question self-test before creating a new skill

Ask yourself:

1. **Does it have parameters that change?** If yes → algorithm (parameters become Bayesian weights). If no → skill.
2. **Will it need to adapt to past user corrections?** If yes → algorithm (Bayesian feedback). If no → skill.
3. **Does it need to work the same way on a different machine?** If yes → algorithm (serialized state). If no → skill.

If 2/3 say "algorithm", write a `medit_*` script + atomic state file, not a new skill.

## Anti-pattern: the `instruction-parser` skill (2026-08-04)

User said: "我需要你修根因，确保每次都完整理解我的指令"

I did exactly the wrong thing: created a skill `instruction-parser` with a 5-step if/else flow that said "always output goal/main_target/constraints/dont_do/verification in this exact format before executing".

User's next message: "这些问题和解决方案是不是都集成到算法里，并同步集成到via54Medit中了"

Sequence to remember:
1. Create `instruction-parser` skill (wrong)
2. Delete it
3. Create `medit_parse_instruction.py` algorithm with Bayesian + Self-Consistency fallback (right)
4. Same correction codified as `medit_decide_correction` Bayesian Beta distribution

The lesson: **if a "remember this rule" feels like the right answer, it's almost always the wrong answer** for via54Medit.

## When skills ARE appropriate (counter-examples)

Not every correction should be an algorithm. Some are pure constants that should stay in skills:

- "H column format must be 8 sections" — industry standard (JAMA, NEJM), not a user preference. → Skill.
- "PDF must be `%PDF` magic bytes" — file format spec, not a user preference. → Skill.
- "sci-hub DDoS-Guard needs 15s sleep" — measured observation. → Skill with measurement log.
- "Local 116.232.74.150 IP, Clash 7890 for foreign sites" — environment-dependent factual state. → Skill (not algorithm).

The rule of thumb: **skills encode facts + domain knowledge, algorithms encode preferences + decisions**.

## File reference

| File | Purpose |
|---|---|
| `~/.medit/scripts/project_layout_resolver.py` | PageRank+EWMA path resolver |
| `~/.medit/scripts/medit_apply_correction.py` | Bayesian Beta decision + fuzzy match |
| `~/.medit/scripts/medit_parse_instruction.py` | Self-Consistency instruction parser |
| `~/.medit/scripts/medit_pdf_archiver.py` | Auto-archive to canonical dir |
| `~/.medit/scripts/medit_citation_updater.py` | H column updater via algorithm |
| `~/.medit/scripts/medit_trainset_accumulator.py` | GEPA trainset accumulator |
| `~/.medit/scripts/medit_mcp_bridge.py` | MCP-compatible tool wrappers |
| `~/.medit/scripts/medit` | Unified CLI |
| `~/.medit/config/project_layout.json` | Schema (no hardcoded paths) |
| `~/.medit/cache/*.json` | Atomic write state |

## Related skills

- `via54medit-algorithm-driven-upgrade-v2` (parent) — the v1.2.0 architecture
- `medit-via54-layout-algorithms` — the algorithm-only umbrella
- `pdf-download-cookbook` — handles the download side, references v25 algorithm
- `algorithm-vs-rules-research-skill` — 6 project comparison (DSPy/SGLang/Aider)
