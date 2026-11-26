# Evaluation log

## 2026-11-26: quantity read from an article
- Problem (dev case `dev-03`): "How much is an 8 inch celebration cake?" extracted quantity 1.
- Change: outside orders, "a" or "an" is no longer read as a quantity.
- Dev field accuracy: 0.929 before, 1.000 after. Test scores unchanged.

## 2026-11-26: drafts quoted whole document sections
- Problem: an order reply listed unrelated text and no price.
- Change: replies quote only the matching sentences; orders also look up price and delivery fee.
- Scores unchanged. Covered by a new test. Reply quality itself is not scored yet (roadmap).
