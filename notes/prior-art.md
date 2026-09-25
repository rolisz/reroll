# Prior art and related work (searched 2026-09-17)

## Closest in spirit

- **Loom** (janus, 2020): tree interface for base-model completions; generate N branches, pick which to continue.
  The "multiverse" framing ("the ways a text might have unfolded") is exactly the "what if I reran it" question,
  but for writing with base models, with no comparison or judging of the branches.
  https://generative.ink/posts/loom-interface-to-the-multiverse/ · https://github.com/socketteer/loom
- **Supporting Sensemaking of LLM Outputs at Scale** (Gero, Swoopes, Gu, Kummerfeld, Glassman, CHI 2024): UI features
  for reading ~10-100 responses to one prompt at once, highlighting what's shared and what differs. Closest research on
  the "look at many samples" UI; aimed at prompt designers, not at a live conversation.
  https://arxiv.org/abs/2401.13726
- **Luminate** (Suh et al., CHI 2024): argues chat UIs push users to converge quickly on a few ideas; generates a
  structured design space of responses instead. Supports "divergence can be the point" (creative/ideation).
  https://github.com/project-luminate/luminate

## Sampling as an uncertainty / hallucination signal (the research behind the labels)

- **SelfCheckGPT** (Manakul et al., EMNLP 2023): if the model knows something, samples agree; hallucinated facts
  diverge and contradict. The Zagreb distances are this effect. https://arxiv.org/abs/2303.08896
- **Semantic entropy** (Kuhn, Gal, Farquhar; Nature 2024): cluster samples by meaning, entropy over clusters flags
  confabulations. reroll's "group by what the replies do, then look at group sizes" is an informal, LLM-judged version.
  https://www.nature.com/articles/s41586-024-07421-0
- **Universal Self-Consistency** (Chen et al., 2023): an LLM picks the most consistent of several free-form samples.
  The opposite design choice to reroll, which shows the spread instead of collapsing it. https://arxiv.org/abs/2311.17311
- **Confidence with multiple correct answers** (2026): disagreement among equally correct answers looks like low
  confidence, indistinguishable from disagreement among wrong ones. The formal version of "different next moves isn't
  a warning". https://arxiv.org/html/2602.07842

## Where conversations fork

- **Forking Paths in Neural Text Generation** (Bigelow et al., ICLR 2025): some single tokens ("forking tokens")
  flip the downstream outcome; models are often one token away from saying something very different.
  https://arxiv.org/abs/2412.07961
- **Priming, Path-dependence, and Plasticity** (2026): 140K real chat sessions; users settle quickly into a small,
  stable repertoire of interaction patterns shaped by early experiences. Path dependence on the user's side.
  https://arxiv.org/abs/2605.05767

## Ambiguity and clarification (the "read you differently" loop)

- **Clarify When Necessary / INTENT-SIM** (Zhang & Choi, 2023): sample responses, group them by equivalence, and use
  entropy over intents to decide when to ask a clarifying question. Very close to reroll's clarification suggestion.
  https://arxiv.org/abs/2311.09469
- **Knowing but Not Showing** (2026): models recognize ambiguity when asked, but in normal answering almost never ask
  clarifying questions. Motivates surfacing ambiguity outside the model's reply. https://arxiv.org/abs/2605.25284

## Diversity / mode collapse (why uniform isn't "correct")

- **Verbalized Sampling** (2025): post-training causes mode collapse (typicality bias in preference data); asking for
  several responses with probabilities restores diversity. Relevant to "Fair challenge —" / "Nice drive —" openings.
  https://arxiv.org/abs/2510.01171

## Everyday tools (compare, branch, regenerate)

- **Branching / regenerate in chat apps**: ChatGPT and Claude keep regenerations and edits as hidden branches;
  GitChat, Branch Agent and LangGraph's branching chat make the tree explicit. None compare or judge the branches.
  https://thepromptbench.com/ai-product-ux/regenerate-undo-branch-conversation-mechanics/ ·
  https://github.com/DrustZ/GitChat · https://docs.langchain.com/oss/python/langchain/frontend/branching-chat
- **Side-by-side comparison**: ChainForge (CHI 2024, prompts × models grids), PAIR's LLM Comparator (two models,
  judged), `llm-compare`. Built for evaluating models/prompts, not for live conversations.
  https://github.com/ianarawjo/ChainForge · https://github.com/PAIR-code/llm-comparator ·
  https://github.com/irthomasthomas/llm-compare

## How reroll differs (for the post)

Research uses sample agreement as a hidden score (hallucination detection, self-consistency); tools either branch
without comparing (Loom, chat apps) or compare models/prompts offline (ChainForge, Comparator). reroll does it
live in an ordinary conversation, on every turn, and shows the spread to the user with a reason (read you differently
vs different next moves vs contradiction) instead of collapsing it into one answer or one number.

Name: a quick search found no LLM tool called "reroll"; check GitHub/PyPI before publishing.
