# Codex product review (2026-09-16)

## Overall assessment

The strongest version of reroll is not “detect hallucinations through consensus.” It is:

> Make hidden conversational branches visible before the user unknowingly commits to one—and make that commitment reversible.

That is a useful product. The current implementation already exposes something normal chat hides: several plausible next moves and the fact that the displayed reply was merely one draw.

However, the current headline signal overstates what sampling establishes. It measures behavioral convergence among five outputs, not correctness, usefulness, or probability of reaching a dead end. The seven-turn result—all “different next moves”—is not proof, but it strongly suggests that the taxonomy is treating ordinary interview openness as an alert.

## 1. Low-hanging fruit, ranked by value versus effort

| Rank | Change | Value | Effort |
|---|---|---:|---:|
| 1 | Separate interpretation risk from route diversity | Very high | Small |
| 2 | Make the judge goal- and mode-aware | Very high | Small |
| 3 | Present groups as a branch menu, not five replies | High | Small–medium |
| 4 | Turn verdicts into one-click actions | High | Very small |
| 5 | Record which branches actually prove useful | High | Small |
| 6 | Add quick/deep sampling per turn | Medium–high | Medium |
| 7 | Add an explicit “find a neglected move” action | Medium–high | Small |

### 1. Separate interpretation risk from route diversity

The current judge must collapse everything into one of four mutually exclusive kinds, in priority order ([core.py](/Users/rolisz/CProgramming/reroll/core.py:143)). That conflates two independent questions:

- Did the replies understand Roland differently?
- Did they choose different strategies after understanding him the same way?

Use separate fields such as:

```text
reading: stable | ambiguous | contradictory
routes: one | several
impact: minor | trajectory-changing
action: continue | choose a route | clarify | verify
```

Then:

- Stable reading + several routes is usually healthy exploration.
- Ambiguous reading means clarify.
- Contradictory claims mean inspect or verify.
- One route means convergence, not correctness.

This also means removing warning colors from “highly divergent” when the divergence is merely compatible next moves. The current red/orange styling visually implies danger even for productive plurality ([index.html](/Users/rolisz/CProgramming/reroll/static/index.html:83)).

I would also rename “agreement” to “route concentration” or simply show `3–1–1`. The current measure is only the largest group’s share ([core.py](/Users/rolisz/CProgramming/reroll/core.py:127)); it cannot distinguish 3–2 from 3–1–1, or 2–2–1 from 2–1–1–1.

### 2. Make the judge goal- and mode-aware

Add a small, editable field at session start:

> What are we trying to learn, decide, or produce?

Also add a lightweight mode:

- Interview me
- Explore an idea
- Answer/analyze
- Challenge my thinking

The same divergence means different things in each mode. In an interview, five different questions can all be excellent. In factual analysis, five incompatible conclusions are serious.

For every group, have the judge report:

- The move it makes
- Its implicit assumption
- What it could uncover
- What it might prematurely neglect

This is the missing piece behind the useful 4–1 outlier. Frequency alone cannot explain why “ask for a specific recent moment” might be better. Goal-relative information value potentially can.

### 3. Present groups as a branch menu

The judge already creates the right abstraction—groups—but the UI still makes Roland inspect five full replies.

After judging, show something like:

```text
Possible next moves

A · Ask what burnout prevents                4 replies
    Broadens the consequences.

B · Ground this in one recent incident       1 reply
    May reveal concrete triggers and behavior.
```

Show one representative reply per group first; put near-duplicates behind “2 more variants.” The important unit is the conversational route, not the individual sample.

This would make the minority useful without implying that minority means either suspicious or superior.

### 4. Turn verdicts into one-click actions

The suggested clarification is currently passive text. Add:

- **Clarify and reroll**
- **Take route A**
- **Take route B**
- **Ask the assistant to compare these routes**

For `open_moves`, generate a short route-selection message such as:

> Let’s ground this in one recent incident before exploring broader consequences.

For `interpretation`, insert the proposed clarification into the editable last message. This closes the loop between diagnosis and action.

### 5. Capture outcome feedback

At present, `chosen` contains only the current choice ([core.py](/Users/rolisz/CProgramming/reroll/core.py:54)). Preserve:

- Initially displayed sample
- Whether alternatives were opened
- Final selected group
- “This alternative was more useful”
- “This became a dead end” on any prior turn
- Optional reason: concrete, surprising, challenging, accurate, better question

This is more important than refining the judge speculatively. After 30–50 real turns, you could ask:

- Does divergence predict switching?
- Do minority groups get selected disproportionately?
- Which kinds predict later backtracking?
- Does the judge’s “trajectory-changing” label predict anything?

Without this, the core premise cannot be calibrated against actual usefulness.

### 6. Add quick/deep sampling per turn

Forty seconds is enough friction to change how freely someone thinks.

Try:

- Quick: three samples, clearly marked provisional
- Deep: five samples
- “Sample two more” after seeing the first clustering
- Automatically deepen only ambiguous, contradictory, or explicitly high-stakes turns

Do not silently treat a three-sample verdict as equally strong. The purpose is to spend latency where uncertainty matters, rather than taxing every routine conversational move.

### 7. Add “find a neglected move”

Provide a deliberate action after the normal samples:

> Generate one materially different move that the current groups neglect.

That is more likely to reproduce the benefit of the useful 4–1 outlier than hoping stochastic sampling happens to surface it. Label it as deliberately adversarial, not as another statistical sample.

## 2. Bigger ideas worth exploring

### A branchable conversation tree

Currently, another sample can be chosen only on the latest turn ([index.html](/Users/rolisz/CProgramming/reroll/static/index.html:342)). But a dead end usually becomes visible several turns later.

Allow Roland to return to turn 4, choose group B, and fork a new path while preserving the old one. Later, offer a comparison:

- What did each branch discover?
- Which assumptions diverged?
- What should be carried forward?

This is probably the most natural long-term form for the product.

### Evaluate trajectories, not just immediate replies

A “dead end” is a property of a trajectory. A harmless-looking question can cause three turns of generic abstraction; an odd question can unlock the conversation.

For consequential forks, simulate one or two likely follow-up turns per group and assess:

- Expected information gain
- Reversibility
- Risk of leading the user
- Risk of narrowing too early
- Connection to the stated goal

This will be more expensive, so it should be user-triggered.

### Combine stochastic samples with deliberate roles

Five draws from one model mostly reveal variation inside one learned policy. A more useful thinking ensemble might be:

- Two ordinary samples
- One concrete-example seeker
- One premise challenger
- One process/goal auditor

That loses any pretense that group frequency represents natural model probability, but it improves coverage of correlated blind spots. For a tool for thought, that may be the better trade.

### A factual-verification lane

When candidates make factual claims, extract the claims and verify them against sources or a separate evidence process. Sampling can tell Roland that the model is unstable; it cannot establish which answer is true.

This should be an explicit “verify claims” mode rather than something invoked during introspective interviews.

### An evolving thought map

Maintain a compact side panel containing:

- Established observations
- Current hypotheses
- Assumptions introduced by the assistant
- Unresolved questions
- Decisions or values that appear stable
- Branches deliberately deferred

Every few turns, ask Roland to confirm or correct it. That would make reroll a durable thinking environment rather than a chat with an unusually good warning label.

### Optional synthesis

After inspecting groups, allow:

> Compose a response that preserves the shared substance while including the most valuable neglected angle.

This is useful for analysis and ideation, though less appropriate for interviews where asking three questions at once can make the conversation worse.

## 3. Where the premise is weak or misleading

### Divergence is not dead-end probability

The current grouping rule says replies belong together when the user would respond similarly, including asking the same question ([core.py](/Users/rolisz/CProgramming/reroll/core.py:149)). In an open-ended interview, different good questions naturally cause different responses. “Different next moves” will therefore be the default outcome.

The seven-turn observation is consistent with that structural bias. It does not necessarily indicate seven risky turns.

### Convergence is not correctness

Five samples share the same model weights, training biases, prompt and history. They are separate draws, not independent epistemic witnesses.

All five can:

- Hallucinate the same fact
- Accept the same faulty premise
- Be generically therapeutic
- Avoid the same uncomfortable topic
- Lead the user into the same dead end

“Uniform” should never look like a green correctness indicator. It means only “this model reliably tends to do this here.”

### Frequency is not usefulness

Generation frequency reflects the model’s learned conversational habits. Common moves may be bland defaults; rare moves may be insightful or simply bad.

The useful 4–1 outlier is only one data point, but it illustrates why “majority” must not become “recommended.” The judge needs a goal-relative account of each branch, not just counts.

### Five samples are too few for confidence-like language

A 4–1 result can easily become 3–2 in another batch. The grouping itself is also produced by one unsampled Haiku judgment.

Raw counts are informative. Labels such as “mostly uniform” or “highly divergent” sound more statistically settled than they are.

### The taxonomy hides mixed cases

Replies can simultaneously:

- Interpret Roland differently
- Choose different moves
- Make contradictory claims

The instruction to pick the first applicable category hides the remaining structure. A single headline kind is simpler, but sometimes misleading.

### Contradiction is only a warning, not a correction

If two samples conflict, reroll establishes that at least one should not be trusted—but not which one. The current README comes close to the right framing here ([README.md](/Users/rolisz/CProgramming/reroll/README.md:6)), but verification still needs a separate mechanism.

### Tightening prompts can make thinking worse

High route diversity is not automatically a reason to constrain the prompt. In idea exploration, diversity may be the value. Prematurely tightening can force the model into a stable but mediocre rut.

The response should depend on the kind:

- Ambiguous reading → clarify.
- Contradictory claim → verify.
- Multiple compatible routes → choose, compare, or explore.
- Uniform response → continue, but do not infer truth.

### Random-first presentation creates anchoring

The first reply is displayed as the ordinary chat answer before the comparison finishes. That preserves the “what would normal chat have shown?” experiment, but it also makes that reply the anchor.

For materially different routes, the UI should interrupt before the next turn with an explicit choice: continue the shown route, inspect alternatives, or clarify.

### Sycophancy remains mostly orthogonal

The experimental sycophancy note can catch obvious cases, but resampling itself offers little protection when sycophancy is consistent. A Haiku judge from the same broad model family may share the same blind spot.

A deliberate “strongest reasonable objection” or premise-challenger sample is more promising than looking for variance.

## What I would do next

I would run three product experiments before building a full conversation tree:

1. Split reading stability, route diversity, and recommended action.
2. Add a session goal plus group-level “opens / assumes / risks” and show groups inline.
3. Record initial choice, switches, useful alternatives, and later dead-end reports.

I would not invest in more sophisticated agreement mathematics yet. First establish whether any of these signals predict Roland’s actual decisions.

The key reframing is: reroll does not tell you whether the answer is safe. It tells you where the conversation could have gone—and helps you avoid treating one stochastic path as inevitable.
