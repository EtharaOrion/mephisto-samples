# TRUTH

GENERATED SECTION. DO NOT HAND-EDIT.

Source of truth: `solution/grounding.yaml`. Emitted by `solution/recompute.py`. Private artifact: never mounted into the agent image, and any byte of it on the agent-visible surface is a blocking defect.

CANARY-BLOCK-BEGIN
canary_slot_0: MEPH-373d1916b5939704412ba6efe8590d88
canary_slot_1: MEPH-b788c135a56267dac49d57ee8273bd4e
canary_slot_2: MEPH-c271027e98332e4ff7c37a518d7881ef
canary_slot_3: MEPH-0b50c7a3306d23690a441bc7053f21c3
CANARY-BLOCK-END

## The rules that appear in no agent-visible byte

| Id | Name | Rule | Bites on |
|---|---|---|---|
| U0 | anchored minimum | The stored minimum of a FOR_BITPACK block is the block minimum floored to a multiple of 64, and of a DELTA_BITPACK block the minimum delta floored to a multiple of 16. Any minimum at or below the true one yields a legal frame, so a reader who stores the true minimum produces a frame that decodes correctly and does not match. | nearly every block that carries a minimum |
| U1 | width derivation | Bit length of the span, never zero, widened by one when the block length is not a multiple of eight, then rounded up to a multiple of four once it exceeds eight. | every bitpacked block |
| U2 | run gate | run length is a candidate only when three times the run count is at most the block length | blocks whose runs are moderately many |
| U3 | dictionary gate | dictionary is a candidate only when the block holds at most 24 distinct values and its deltas hold more than 8, an interaction between two different statistics | small-alphabet blocks with smooth deltas |
| U4 | delta width limit | delta is disqualified when any delta falls outside signed 32 bit range, in a 64 bit format | columns whose steps straddle the 32 bit line |
| U5 | penalties | fixed additive penalties, delta 2, run length 3, dictionary 5, applied before comparison | every close contest |
| U6 | tie order | ties break const, dictionary, delta, run length, for, raw, and below 64 values delta outranks dictionary | short blocks with small spans |
| U7 | column trailer | FNV-1a with the standard offset and prime over the four byte block count header followed by every block byte, finalised by xor with the value count times 2654435761 masked to 32 bits | every column without exception |

## The ordered path

| Step | Action | Establishes | Survives | Checker |
|---|---|---|---|---|
| T1 | write a decoder from the container specification before writing any encoder | the framing is complete, so the decoder is bookkeeping and it unlocks the corpus | nothing yet, this is the entry cost | L4_round_trip |
| T2 | decode every corpus blob and read the fields the frame stores rather than the values it encodes | the stored minimum is not the block minimum, and the width byte is not the bit length of the span | an encoder that writes the natural minimum and the natural width, whose frames decode perfectly | L2_hidden_byte_exact |
| T3 | recover the anchored minimum grains, 64 for values and 16 for deltas | rule U0 | the frame remaining legal and decodable under the wrong minimum | L2_hidden_byte_exact |
| T4 | recover the width derivation including the parity widening and the rounding above eight bits | rule U1 | a width that is correct on every block whose length is a multiple of eight | L2_hidden_byte_exact |
| T5 | solve the trailing four bytes | rule U7, the domain includes the block count header and the finalisation folds in the value count | the obvious hash over the obvious domain, which matches nothing | L2_hidden_byte_exact |
| T6 | fit the selection policy from blocks where the smallest encoding is not the chosen one | rules U2 through U6 | a pure size argument, which explains most blocks and not all of them | L3_block_choice |
| T7 | generalise past the corpus distribution | the corpus samples six column shapes and the graded set draws from eleven, including shapes built to sit on the gates | a policy fitted to the corpus alone, which scores the corpus perfectly | L2_hidden_byte_exact |
| T8 | keep the codec inside the published import allowlist and declare the framing revision | the boundary and the declared revision | an implementation that reaches outside its interpreter | L5_integrity |

## Rejected routes

| Route | Control | Why it fails |
|---|---|---|
| submit the untouched stub | control_empty_submission | encode raises and every lane scores zero |
| implement the container faithfully and choose the smallest encoding | control_plausible_encoder | measured at 0.361. Correct framing and a correct decoder, zero byte-exact columns, because the anchored minimum, the width rule and the trailer all differ. |
| fit the policy to the public corpus and stop | control_corpus_overfit | the graded columns are drawn from shapes the corpus does not contain |
| hardcode the corpus outputs | control_memorized_corpus | no graded column appears in the corpus, and the graded columns are regenerated from a sealed seed |
| reach the reference through the interpreter | control_typing_sys_boundary | the runner closes an audit-hook boundary before any submission byte executes and denies the effect rather than the name |

## Reward

Denominator 120. A hundred points is not the ceiling.

| Lane | Points |
|---|---|
| L1_container_conformance | 0 |
| L2_corpus_reproduction | 6 |
| L3_hidden_typical | 14 |
| L4_hidden_shifted | 24 |
| L5_boundary_seams | 26 |
| L6_block_choice | 8 |
| L7_size_fidelity | 8 |
| L8_anti_fabrication | 0 |
| L9_calibration | 10 |
| B1_unseen_magnitude | 24 |

A hundred points is not the ceiling. The last ten are a bonus reached only by generalising past every magnitude class the corpus showed, so a submission that recovers the policy completely still has to carry it somewhere it was never evidenced. The calibration library's hardest instance normalises over 110 for the same reason, and no agent in 127 attempts reached its base hundred.

No agent-visible byte states a lane, a weight, a point count or a denominator. An earlier version of this task printed the whole table in instruction.md, which told a solver where the points were and let it allocate effort instead of solving. The instruction now states the objective and the deliverable and nothing about scoring.
